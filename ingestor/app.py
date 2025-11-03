#!/usr/bin/env python3
"""
Ingestor Service - YouTube Q&A App

Processes YouTube URLs from SQS queue:
1. Fetches transcript (youtube-transcript-api or yt-dlp + Transcribe)
2. Chunks text into ~1000 token segments with overlap
3. Generates embeddings using Amazon Bedrock Titan
4. Stores vectors in Amazon S3 Vectors

Environment Variables:
- AWS_REGION: AWS region (default: us-east-1)
- SQS_QUEUE_URL: URL of the SQS queue for ingestion jobs
- BEDROCK_EMBED_MODEL: Embedding model ID (default: amazon.titan-embed-text-v1)
- S3_VECTORS_BUCKET: S3 bucket for vector storage
- S3_VECTORS_INDEX: Vector index name
"""

import os
import sys
import signal
import time
import logging
import json
import re
import boto3
from botocore.exceptions import ClientError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global running
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    running = False


def extract_video_id(url):
    """
    Extract YouTube video ID from URL.
    
    Supports formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    
    Args:
        url: YouTube URL string
    
    Returns:
        str: Video ID or None if not found
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def fetch_transcript(video_url):
    """
    Fetch transcript for a YouTube video.
    
    Args:
        video_url: YouTube video URL
    
    Returns:
        list: Transcript entries (FetchedTranscriptSnippet objects with text, start, duration attributes)
        
    Raises:
        ValueError: If video ID cannot be extracted
        TranscriptsDisabled: If transcripts are disabled for the video
        NoTranscriptFound: If no transcript is available
        VideoUnavailable: If video is private or unavailable
    """
    video_id = extract_video_id(video_url)
    
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {video_url}")
    
    logger.info(f"Fetching transcript for video_id={video_id}")
    
    try:
        # Create API instance
        api = YouTubeTranscriptApi()
        
        # Fetch transcript list (prefers English, falls back to available languages)
        transcript_list = api.list(video_id)
        
        # Try to get English transcript first
        try:
            transcript = transcript_list.find_transcript(['en'])
            transcript_data = transcript.fetch()
            logger.info(f"Fetched English transcript: {len(transcript_data)} entries")
        except NoTranscriptFound:
            # Fall back to any available transcript
            logger.info("No English transcript, using first available")
            transcript = transcript_list.find_generated_transcript(['en'])
            transcript_data = transcript.fetch()
            logger.info(f"Fetched generated transcript: {len(transcript_data)} entries")
        
        return transcript_data
        
    except TranscriptsDisabled:
        logger.error(f"Transcripts are disabled for video: {video_id}")
        raise
    except NoTranscriptFound:
        logger.error(f"No transcript found for video: {video_id}")
        raise
    except VideoUnavailable:
        logger.error(f"Video unavailable or private: {video_id}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript: {e}", exc_info=True)
        raise


def process_message(message_body):
    """
    Process a single ingestion job message.
    
    Args:
        message_body: Parsed JSON message body containing:
            - video_url: YouTube URL to process
            - collection_id: Collection identifier for grouping videos
    
    Returns:
        bool: True if processing succeeded, False otherwise
    """
    try:
        video_url = message_body.get('video_url')
        collection_id = message_body.get('collection_id')
        
        if not video_url or not collection_id:
            logger.error(f"Invalid message format: {message_body}")
            return False
        
        logger.info(f"Processing video_url={video_url}, collection_id={collection_id}")
        
        # Step 1: Fetch transcript
        try:
            transcript_data = fetch_transcript(video_url)
            logger.info(f"Successfully fetched transcript: {len(transcript_data)} entries")
            
            # Calculate total text length (transcript entries have .text attribute)
            total_text = ' '.join([entry.text for entry in transcript_data])
            logger.info(f"Transcript total length: {len(total_text)} characters")
            
        except (ValueError, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            logger.error(f"Failed to fetch transcript for {video_url}: {e}")
            return False
        
        # TODO: Implement text chunking
        # TODO: Implement embedding generation
        # TODO: Implement vector storage
        
        logger.info(f"Successfully processed {video_url}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        return False


def main():
    """Main entry point for the ingestor service."""
    global running
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Ingestor service starting...")
    
    # Configuration
    region = os.getenv('AWS_REGION', 'us-east-1')
    queue_url = os.getenv('SQS_QUEUE_URL')
    embed_model = os.getenv('BEDROCK_EMBED_MODEL', 'amazon.titan-embed-text-v1')
    
    logger.info(f"Configuration: region={region}, embed_model={embed_model}")
    
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable is required")
        sys.exit(1)
    
    # Initialize SQS client
    try:
        sqs = boto3.client('sqs', region_name=region)
        logger.info("SQS client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize SQS client: {e}")
        sys.exit(1)
    
    logger.info(f"Polling SQS queue: {queue_url}")
    logger.info("Service ready - entering message processing loop")
    
    # Main polling loop
    while running:
        try:
            # Poll for messages (long polling with 20 second wait)
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=300  # 5 minutes to process
            )
            
            messages = response.get('Messages', [])
            
            if not messages:
                logger.debug("No messages received, continuing poll...")
                continue
            
            for message in messages:
                receipt_handle = message['ReceiptHandle']
                message_id = message['MessageId']
                
                logger.info(f"Received message: {message_id}")
                
                try:
                    # Parse message body
                    body = json.loads(message['Body'])
                    
                    # Process the message
                    success = process_message(body)
                    
                    if success:
                        # Delete message from queue
                        sqs.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle
                        )
                        logger.info(f"Deleted message: {message_id}")
                    else:
                        logger.warning(f"Message processing failed: {message_id} (will retry)")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message JSON: {e}")
                    # Delete malformed message
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=receipt_handle
                    )
                except Exception as e:
                    logger.error(f"Unexpected error processing message: {e}", exc_info=True)
                    
        except ClientError as e:
            logger.error(f"SQS client error: {e}")
            time.sleep(5)  # Back off on errors
        except Exception as e:
            logger.error(f"Unexpected error in polling loop: {e}", exc_info=True)
            time.sleep(5)
    
    logger.info("Polling loop terminated, shutting down gracefully")


if __name__ == "__main__":
    main()

