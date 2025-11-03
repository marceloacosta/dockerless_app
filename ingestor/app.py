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
import boto3
from botocore.exceptions import ClientError

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
        
        # TODO: Implement transcript fetching
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

