# QA API Service

REST API for querying YouTube video transcripts using Amazon Bedrock Knowledge Base RAG (Retrieval Augmented Generation).

## Overview

This service provides a FastAPI-based HTTP API that:
1. Accepts natural language questions about indexed YouTube videos
2. Queries the Bedrock Knowledge Base to retrieve relevant transcript chunks
3. Uses a foundation model (Claude 3 Haiku) to generate accurate answers
4. Returns answers with source citations

## Architecture

```
User Request → FastAPI → Bedrock RetrieveAndGenerate → Knowledge Base (S3 Vectors)
                              ↓
                    Claude 3 Haiku (Generation)
                              ↓
                    Response with Citations
```

## API Endpoints

### `POST /query`

Ask a question about indexed videos.

**Request:**
```json
{
  "question": "What is this video about?",
  "video_id": "dQw4w9WgXcQ"  // optional
}
```

**Response:**
```json
{
  "answer": "Generated answer text based on video transcripts...",
  "sources": [
    {
      "s3_uri": "s3://YOUR-KB-BUCKET/dQw4w9WgXcQ.txt",
      "chunk_id": "cb8615b2-1315-4a8b-9112-b275487487c4",
      "excerpt": "Relevant text excerpt from the transcript...",
      "video_id": "dQw4w9WgXcQ"
    }
  ],
  "session_id": "unique-session-id"
}
```

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "aws_region": "us-east-1",
  "kb_id": "YOUR_KB_ID"
}
```

### `GET /`

Root endpoint with API information.

### `GET /docs`

Interactive API documentation (Swagger UI).

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_REGION` | No | `us-east-1` | AWS region for Bedrock |
| `KB_ID` | Yes | - | Bedrock Knowledge Base ID |
| `BEDROCK_MODEL_ARN` | Yes | - | ARN of the LLM for generation |

### Example Configuration

```bash
export AWS_REGION=us-east-1
export KB_ID=YOUR_KB_ID
export BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0
```

## Local Development

### Prerequisites

- Python 3.11+
- AWS credentials configured
- Access to Bedrock Knowledge Base

### Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export KB_ID=YOUR_KB_ID
export BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0

# Run the service
uvicorn app:app --reload --port 8000
```

### Testing

```bash
# Health check
curl http://localhost:8000/health

# Query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is this video about?"
  }'

# Access interactive docs
open http://localhost:8000/docs
```

## Container Build

### Build Image (without Docker)

```bash
# Using buildah (rootless)
buildah bud -t youtube-qa-api:latest .

# Using podman
podman build -t youtube-qa-api:latest .
```

### Run Container

```bash
# Using podman
podman run -d \
  --name qa-api \
  -p 8000:8000 \
  -e AWS_REGION=us-east-1 \
  -e KB_ID=YOUR_KB_ID \
  -e BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0 \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  youtube-qa-api:latest
```

## Deployment

This service is designed to run as a containerized application on:
- **AWS ECS Fargate** (recommended for production)
- **AWS App Runner** (simplest managed option)
- **AWS ECS EC2** (more control over compute)
- Local container runtime (development/testing)

## Features

✅ **RAG-powered responses** - Accurate answers grounded in video transcripts  
✅ **Source citations** - Every answer includes source references  
✅ **Deduplication** - Removes duplicate source chunks  
✅ **Error handling** - Graceful error responses for API failures  
✅ **Health checks** - Built-in health endpoint and container healthcheck  
✅ **Interactive docs** - Automatic Swagger UI at `/docs`  
✅ **Structured logging** - JSON-formatted logs for observability  
✅ **Non-root container** - Security best practices  

## Architecture Notes

### Why FastAPI?
- Modern, fast Python web framework
- Automatic OpenAPI/Swagger documentation
- Built-in request/response validation with Pydantic
- Async support for better performance
- Easy to test and maintain

### Why Container vs. Lambda?
This project demonstrates containerization patterns. While Lambda + API Gateway would be more "serverless," containers showcase:
- Consistent deployment model with the ingestor service
- "Containerization without Docker" theme
- Different patterns (background worker + HTTP API)

## License

Part of the YouTube Q&A Dockerless App project.

