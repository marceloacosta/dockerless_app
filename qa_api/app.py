#!/usr/bin/env python3
"""
QA API Service - YouTube Q&A App

Provides REST API for querying YouTube video transcripts using
Amazon Bedrock Knowledge Base RAG.

Endpoints:
- POST /query: Ask questions about indexed videos
- GET /health: Health check

Environment Variables:
- AWS_REGION: AWS region (default: us-east-1)
- KB_ID: Bedrock Knowledge Base ID (required)
- BEDROCK_MODEL_ARN: Model ARN for generation (required)
"""

import os
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="YouTube Q&A API",
    description="RAG-powered question answering for YouTube video transcripts",
    version="1.0.0",
    root_path="/api"  # Handle ALB routing prefix
)

# Configuration
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
KB_ID = os.getenv('KB_ID')
BEDROCK_MODEL_ARN = os.getenv('BEDROCK_MODEL_ARN')

# Validate required configuration
if not KB_ID:
    raise ValueError("KB_ID environment variable is required")
if not BEDROCK_MODEL_ARN:
    raise ValueError("BEDROCK_MODEL_ARN environment variable is required")

# Initialize Bedrock client
try:
    bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=AWS_REGION)
    logger.info(f"Bedrock client initialized for region {AWS_REGION}")
except Exception as e:
    logger.error(f"Failed to initialize Bedrock client: {e}")
    raise


# Request/Response Models
class QueryRequest(BaseModel):
    """Request model for /query endpoint."""
    question: str = Field(..., description="Question to ask about the videos", min_length=1)
    video_id: Optional[str] = Field(None, description="Optional: specific video ID to query")


class SourceReference(BaseModel):
    """Source reference from Knowledge Base."""
    s3_uri: str = Field(..., description="S3 URI of source document")
    chunk_id: str = Field(..., description="Unique chunk identifier")
    excerpt: str = Field(..., description="Relevant text excerpt from source")
    video_id: Optional[str] = Field(None, description="Extracted video ID if available")


class QueryResponse(BaseModel):
    """Response model for /query endpoint."""
    answer: str = Field(..., description="Generated answer to the question")
    sources: List[SourceReference] = Field(..., description="Source references used")
    session_id: str = Field(..., description="Unique session identifier")


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""
    status: str = Field(..., description="Service status")
    aws_region: str = Field(..., description="Configured AWS region")
    kb_id: str = Field(..., description="Knowledge Base ID")


# Helper Functions
def extract_video_id_from_uri(s3_uri: str) -> Optional[str]:
    """
    Extract video ID from S3 URI.
    
    URI format: s3://bucket-name/VIDEO_ID.txt
    
    Args:
        s3_uri: S3 URI string
        
    Returns:
        Video ID or None if not found
    """
    try:
        # Extract filename from URI
        filename = s3_uri.split('/')[-1]
        # Remove .txt extension
        video_id = filename.replace('.txt', '')
        return video_id if video_id else None
    except Exception:
        return None


def parse_bedrock_response(response: dict) -> QueryResponse:
    """
    Parse Bedrock RetrieveAndGenerate response into QueryResponse.
    
    Args:
        response: Raw response from Bedrock API
        
    Returns:
        Parsed QueryResponse object
    """
    # Extract answer text
    answer = response['output']['text']
    
    # Extract session ID
    session_id = response.get('sessionId', '')
    
    # Parse citations and build source list
    sources = []
    seen_chunks = set()  # Deduplicate by chunk_id
    
    for citation in response.get('citations', []):
        for ref in citation.get('retrievedReferences', []):
            chunk_id = ref['metadata'].get('x-amz-bedrock-kb-chunk-id', '')
            
            # Skip if we've already seen this chunk
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)
            
            # Extract S3 URI
            s3_uri = ref['location']['s3Location']['uri']
            
            # Extract text excerpt (limit to 500 chars for response size)
            excerpt = ref['content']['text'][:500]
            if len(ref['content']['text']) > 500:
                excerpt += '...'
            
            # Try to extract video ID from URI
            video_id = extract_video_id_from_uri(s3_uri)
            
            sources.append(SourceReference(
                s3_uri=s3_uri,
                chunk_id=chunk_id,
                excerpt=excerpt,
                video_id=video_id
            ))
    
    return QueryResponse(
        answer=answer,
        sources=sources,
        session_id=session_id
    )


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns service status and configuration.
    """
    return HealthResponse(
        status="healthy",
        aws_region=AWS_REGION,
        kb_id=KB_ID
    )


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Query the Knowledge Base with a question.
    
    Uses Amazon Bedrock RetrieveAndGenerate to:
    1. Retrieve relevant transcript chunks from Knowledge Base
    2. Generate an answer using the specified LLM
    3. Return answer with source citations
    
    Args:
        request: QueryRequest with question and optional video_id
        
    Returns:
        QueryResponse with answer, sources, and session_id
        
    Raises:
        HTTPException: If the query fails
    """
    logger.info(f"Received query: {request.question}")
    
    try:
        # Build request payload
        payload = {
            "input": {
                "text": request.question
            },
            "retrieveAndGenerateConfiguration": {
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KB_ID,
                    "modelArn": BEDROCK_MODEL_ARN
                }
            }
        }
        
        # TODO: If video_id is provided, add filter to retrieve only from that document
        # This would require metadata filtering in the retrieveAndGenerateConfiguration
        
        # Call Bedrock RetrieveAndGenerate API
        response = bedrock_agent_runtime.retrieve_and_generate(**payload)
        
        logger.info(f"Bedrock response received, session_id={response.get('sessionId')}")
        
        # Parse and return response
        return parse_bedrock_response(response)
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Bedrock API error: {error_code} - {error_message}")
        raise HTTPException(
            status_code=500,
            detail=f"Bedrock API error: {error_message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=== YouTube Q&A API Starting ===")
    logger.info(f"AWS Region: {AWS_REGION}")
    logger.info(f"Knowledge Base ID: {KB_ID}")
    logger.info(f"Model ARN: {BEDROCK_MODEL_ARN}")
    logger.info("=== API Ready ===")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "YouTube Q&A API",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /health",
            "query": "POST /query",
            "docs": "GET /docs"
        }
    }

