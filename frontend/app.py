#!/usr/bin/env python3
"""
Frontend Service - YouTube Q&A App

Simple web interface for:
1. Submitting YouTube URLs for ingestion
2. Asking questions about indexed videos

Environment Variables:
- AWS_REGION: AWS region (default: us-east-1)
- SQS_QUEUE_URL: URL of the SQS queue for ingestion jobs
- QA_API_URL: URL of the QA API service (default: http://localhost:8000)
- FLASK_PORT: Port to run on (default: 3000)
"""

import os
import logging
from flask import Flask, request, jsonify, send_from_directory
import boto3
from botocore.exceptions import ClientError
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')

# Configuration
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL')
QA_API_URL = os.getenv('QA_API_URL', 'http://localhost:8000')
FLASK_PORT = int(os.getenv('FLASK_PORT', 3000))

# Initialize SQS client
try:
    sqs = boto3.client('sqs', region_name=AWS_REGION)
    logger.info(f"SQS client initialized for region {AWS_REGION}")
except Exception as e:
    logger.error(f"Failed to initialize SQS client: {e}")
    sqs = None


@app.route('/')
def index():
    """Serve the main HTML page."""
    return send_from_directory('static', 'index.html')


@app.route('/ingest', methods=['POST'])
def ingest():
    """
    Submit a YouTube URL for ingestion.
    
    Request body:
    {
        "video_url": "https://www.youtube.com/watch?v=..."
    }
    
    Returns:
    {
        "success": true,
        "message": "Video submitted for ingestion",
        "message_id": "..."
    }
    """
    if not SQS_QUEUE_URL:
        return jsonify({
            'success': False,
            'error': 'SQS_QUEUE_URL not configured'
        }), 500
    
    if not sqs:
        return jsonify({
            'success': False,
            'error': 'SQS client not initialized'
        }), 500
    
    try:
        data = request.get_json()
        video_url = data.get('video_url')
        
        if not video_url:
            return jsonify({
                'success': False,
                'error': 'video_url is required'
            }), 400
        
        # Send message to SQS
        message_body = {
            'video_url': video_url,
            'collection_id': 'default'
        }
        
        response = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=str(message_body).replace("'", '"')
        )
        
        logger.info(f"Sent video URL to SQS: {video_url}")
        
        return jsonify({
            'success': True,
            'message': 'Video submitted for ingestion',
            'message_id': response['MessageId']
        })
        
    except ClientError as e:
        logger.error(f"SQS error: {e}")
        return jsonify({
            'success': False,
            'error': f'SQS error: {e.response["Error"]["Message"]}'
        }), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/query', methods=['POST'])
def query():
    """
    Ask a question about indexed videos.
    
    Request body:
    {
        "question": "What is this video about?"
    }
    
    Returns:
    {
        "success": true,
        "answer": "...",
        "sources": [...],
        "session_id": "..."
    }
    """
    try:
        data = request.get_json()
        question = data.get('question')
        
        if not question:
            return jsonify({
                'success': False,
                'error': 'question is required'
            }), 400
        
        # Call QA API
        qa_response = requests.post(
            f'{QA_API_URL}/query',
            json={'question': question},
            timeout=30
        )
        
        if qa_response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'QA API error: {qa_response.text}'
            }), qa_response.status_code
        
        qa_data = qa_response.json()
        
        logger.info(f"Query answered: {question[:50]}...")
        
        return jsonify({
            'success': True,
            'answer': qa_data['answer'],
            'sources': qa_data['sources'],
            'session_id': qa_data['session_id']
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"QA API request error: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to reach QA API: {str(e)}'
        }), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/clear', methods=['POST'])
def clear_videos():
    """
    Clear all videos from the Knowledge Base.
    
    Deletes all transcript files from S3 and triggers KB sync.
    
    Returns:
    {
        "success": true,
        "message": "All videos cleared",
        "deleted_count": 3
    }
    """
    # Configuration for KB
    kb_bucket = os.getenv('KB_BUCKET')
    if not kb_bucket:
        logger.error("KB_BUCKET environment variable is required")
        return jsonify({"success": False, "error": "KB_BUCKET not configured"}), 500
    kb_id = os.getenv('KB_ID')
    kb_data_source_id = os.getenv('KB_DATA_SOURCE_ID')
    
    if not kb_id or not kb_data_source_id:
        return jsonify({
            'success': False,
            'error': 'KB_ID and KB_DATA_SOURCE_ID not configured'
        }), 500
    
    try:
        # Initialize S3 and Bedrock Agent clients
        s3 = boto3.client('s3', region_name=AWS_REGION)
        bedrock_agent = boto3.client('bedrock-agent', region_name=AWS_REGION)
        
        # List all objects in the bucket
        response = s3.list_objects_v2(Bucket=kb_bucket)
        objects = response.get('Contents', [])
        deleted_count = 0
        
        # Delete all objects
        if objects:
            delete_keys = [{'Key': obj['Key']} for obj in objects]
            s3.delete_objects(
                Bucket=kb_bucket,
                Delete={'Objects': delete_keys}
            )
            deleted_count = len(delete_keys)
            logger.info(f"Deleted {deleted_count} files from {kb_bucket}")
        
        # Trigger Knowledge Base sync to update the index
        sync_response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=kb_data_source_id
        )
        
        ingestion_job_id = sync_response['ingestionJob']['ingestionJobId']
        logger.info(f"Started KB sync job: {ingestion_job_id}")
        
        return jsonify({
            'success': True,
            'message': f'All videos cleared ({deleted_count} files deleted)',
            'deleted_count': deleted_count,
            'ingestion_job_id': ingestion_job_id
        })
        
    except ClientError as e:
        logger.error(f"AWS error: {e}")
        return jsonify({
            'success': False,
            'error': f'AWS error: {e.response["Error"]["Message"]}'
        }), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'aws_region': AWS_REGION,
        'sqs_configured': bool(SQS_QUEUE_URL),
        'qa_api_url': QA_API_URL
    })


if __name__ == '__main__':
    logger.info("=== YouTube Q&A Frontend Starting ===")
    logger.info(f"AWS Region: {AWS_REGION}")
    logger.info(f"SQS Queue URL: {SQS_QUEUE_URL or 'Not configured'}")
    logger.info(f"QA API URL: {QA_API_URL}")
    logger.info(f"Running on http://localhost:{FLASK_PORT}")
    logger.info("=== Frontend Ready ===")
    
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=True)

