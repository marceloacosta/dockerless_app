#!/usr/bin/env python3
"""
Ingestor Service - YouTube Q&A App

Processes YouTube URLs from SQS queue:
1. Fetches transcript using youtube-transcript-api
2. Uploads transcript to S3 as plain text document
3. Triggers Bedrock Knowledge Base sync to generate embeddings
4. Embeddings stored in S3 Vectors via Bedrock KB

Environment Variables:
- AWS_REGION: AWS region (default: us-east-1)
- SQS_QUEUE_URL: URL of the SQS queue for ingestion jobs
- KB_BUCKET: S3 bucket for transcript documents (default: YOUR-KB-BUCKET)
- KB_ID: Bedrock Knowledge Base ID
- KB_DATA_SOURCE_ID: Knowledge Base Data Source ID
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
        
        # Fetch transcript list
        transcript_list = api.list(video_id)
        
        # Try to get English transcript first (preferred)
        try:
            transcript = transcript_list.find_transcript(['en'])
            transcript_data = transcript.fetch()
            logger.info(f"Fetched English transcript: {len(transcript_data)} entries")
        except NoTranscriptFound:
            # Fallback: Get ANY available transcript (any language)
            # Bedrock's LLM can handle multilingual content
            logger.info("No English transcript found, fetching first available transcript...")
            available = transcript_list._manually_created_transcripts or transcript_list._generated_transcripts
            if available:
                first_transcript = list(available.values())[0]
                transcript_data = first_transcript.fetch()
                language = first_transcript.language
                logger.info(f"Fetched transcript in {language}: {len(transcript_data)} entries (LLM will handle language)")
            else:
                raise NoTranscriptFound("No transcripts available for this video")
        
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


def format_transcript_document(video_id, video_url, transcript_data):
    """
    Format transcript data as a plain text document with metadata.
    
    Args:
        video_id: YouTube video ID
        video_url: Full YouTube URL
        transcript_data: List of transcript entries
    
    Returns:
        str: Formatted document text
    """
    # Build document with metadata header
    lines = [
        f"Video ID: {video_id}",
        f"URL: {video_url}",
        "",
        "=== TRANSCRIPT ===",
        ""
    ]
    
    # Add transcript text with timestamps
    for entry in transcript_data:
        timestamp = int(entry.start)
        minutes = timestamp // 60
        seconds = timestamp % 60
        lines.append(f"[{minutes:02d}:{seconds:02d}] {entry.text}")
    
    return '\n'.join(lines)


def upload_to_s3_and_sync(video_id, video_url, transcript_data, s3_client, bedrock_agent_client, kb_bucket, kb_id, kb_data_source_id):
    """
    Upload transcript to S3 and trigger Knowledge Base sync.
    
    Args:
        video_id: YouTube video ID
        video_url: Full YouTube URL
        transcript_data: List of transcript entries
        s3_client: Boto3 S3 client
        bedrock_agent_client: Boto3 Bedrock Agent client
        kb_bucket: S3 bucket name for transcripts
        kb_id: Knowledge Base ID
        kb_data_source_id: Data Source ID
    
    Returns:
        str: Ingestion job ID
        
    Raises:
        ClientError: If S3 upload or KB sync fails
    """
    # Format transcript as text document
    document_text = format_transcript_document(video_id, video_url, transcript_data)
    
    # S3 key: {video_id}.txt
    s3_key = f"{video_id}.txt"
    
    logger.info(f"Uploading transcript to s3://{kb_bucket}/{s3_key}")
    
    # Upload to S3
    s3_client.put_object(
        Bucket=kb_bucket,
        Key=s3_key,
        Body=document_text.encode('utf-8'),
        ContentType='text/plain'
    )
    
    logger.info(f"Upload successful, triggering Knowledge Base sync")
    
    # Trigger Knowledge Base ingestion job
    response = bedrock_agent_client.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=kb_data_source_id
    )
    
    ingestion_job_id = response['ingestionJob']['ingestionJobId']
    logger.info(f"Ingestion job started: {ingestion_job_id}")
    
    return ingestion_job_id


def process_message(message_body, s3_client, bedrock_agent_client, kb_bucket, kb_id, kb_data_source_id):
    """
    Process a single ingestion job message.
    
    Args:
        message_body: Parsed JSON message body containing:
            - video_url: YouTube URL to process
            - collection_id: Collection identifier for grouping videos
        s3_client: Boto3 S3 client
        bedrock_agent_client: Boto3 Bedrock Agent client
        kb_bucket: S3 bucket for transcripts
        kb_id: Knowledge Base ID
        kb_data_source_id: Data Source ID
    
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
        
        # Step 2: Upload to S3 and trigger Knowledge Base sync
        try:
            video_id = extract_video_id(video_url)
            ingestion_job_id = upload_to_s3_and_sync(
                video_id, 
                video_url, 
                transcript_data,
                s3_client,
                bedrock_agent_client,
                kb_bucket,
                kb_id,
                kb_data_source_id
            )
            logger.info(f"Document indexed, ingestion_job_id={ingestion_job_id}")
            
        except ClientError as e:
            logger.error(f"Failed to upload or sync: {e}")
            return False
        
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
    kb_bucket = os.getenv('KB_BUCKET', 'YOUR-KB-BUCKET')
    kb_id = os.getenv('KB_ID')
    kb_data_source_id = os.getenv('KB_DATA_SOURCE_ID')
    
    logger.info(f"Configuration: region={region}, kb_bucket={kb_bucket}")
    
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable is required")
        sys.exit(1)
    
    if not kb_id or not kb_data_source_id:
        logger.error("KB_ID and KB_DATA_SOURCE_ID environment variables are required")
        sys.exit(1)
    
    # Initialize AWS clients
    try:
        sqs = boto3.client('sqs', region_name=region)
        s3 = boto3.client('s3', region_name=region)
        bedrock_agent = boto3.client('bedrock-agent', region_name=region)
        logger.info("AWS clients initialized (SQS, S3, Bedrock Agent)")
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {e}")
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
                    success = process_message(body, s3, bedrock_agent, kb_bucket, kb_id, kb_data_source_id)
                    
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

