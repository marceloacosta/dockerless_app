# Frontend Service

Web interface for the YouTube Q&A application. Allows users to submit YouTube URLs for ingestion and ask questions about indexed videos.

## Overview

Simple, modern web UI built with:
- **Backend:** Flask (Python)
- **Frontend:** Vanilla HTML/CSS/JavaScript (no frameworks)
- **Design:** Clean, responsive, gradient theme

## Features

### 1. Video Ingestion
- Submit YouTube URLs via web form
- URLs are sent to SQS queue for processing
- Real-time feedback on submission status

### 2. Question Answering
- Ask natural language questions
- Receives AI-generated answers from QA API
- Displays source citations with excerpts

### 3. User Experience
- Clean, modern interface with purple gradient theme
- Responsive design (works on mobile)
- Real-time status updates
- Smooth animations and transitions

## Architecture

```
User Browser
    ↓ (HTTP)
Flask Server (Port 3000)
    ↓
    ├─→ /api/ingest → SQS Queue → Ingestor Service
    └─→ /api/query → QA API (Port 8000) → Bedrock KB
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_REGION` | No | `us-east-1` | AWS region |
| `SQS_QUEUE_URL` | Yes | - | URL of ingestion queue |
| `QA_API_URL` | No | `http://localhost:8000` | QA API endpoint |
| `FLASK_PORT` | No | `3000` | Port to run on |

### Example Configuration

```bash
export AWS_REGION=us-east-1
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/YOUR_ACCOUNT_ID/youtube-qa-ingestor
export QA_API_URL=http://localhost:8000
export FLASK_PORT=3000
```

## Local Development

### Prerequisites

- Python 3.11+
- AWS credentials configured
- QA API service running on port 8000
- Ingestor service running

### Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/YOUR_ACCOUNT_ID/youtube-qa-ingestor
export QA_API_URL=http://localhost:8000

# Run the service
python app.py
```

### Access

Open browser to: **http://localhost:3000**

## API Endpoints

### Backend API Routes

#### `GET /`
Serves the main HTML page.

#### `POST /api/ingest`
Submit YouTube URL for ingestion.

**Request:**
```json
{
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Video submitted for ingestion",
  "message_id": "f0ad43a7-..."
}
```

#### `POST /api/query`
Ask a question about indexed videos.

**Request:**
```json
{
  "question": "What is this video about?"
}
```

**Response:**
```json
{
  "success": true,
  "answer": "Generated answer text...",
  "sources": [
    {
      "s3_uri": "s3://...",
      "chunk_id": "...",
      "excerpt": "...",
      "video_id": "dQw4w9WgXcQ"
    }
  ],
  "session_id": "..."
}
```

#### `GET /api/health`
Health check endpoint.

## Testing the Complete Flow

### Terminal 1: Start Ingestor
```bash
cd ingestor
source .venv/bin/activate
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...
export KB_ID=YOUR_KB_ID
export KB_DATA_SOURCE_ID=YOUR_DATA_SOURCE_ID
python app.py
```

### Terminal 2: Start QA API
```bash
cd qa_api
source .venv/bin/activate
export KB_ID=YOUR_KB_ID
export BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0
uvicorn app:app --port 8000
```

### Terminal 3: Start Frontend
```bash
cd frontend
source .venv/bin/activate
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...
python app.py
```

### Test Flow:
1. Open http://localhost:3000
2. Submit a YouTube URL (e.g., `https://www.youtube.com/watch?v=dQw4w9WgXcQ`)
3. Wait ~30 seconds for processing
4. Ask a question (e.g., "What is this video about?")
5. View the AI-generated answer with sources

## Project Structure

```
frontend/
├── app.py                 # Flask backend
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── static/
    ├── index.html        # Main UI
    ├── style.css         # Styling
    └── app.js            # Frontend logic
```

## Design Decisions

### Why Flask?
- Lightweight and simple
- Perfect for serving static files + API proxy
- Easy to containerize
- Minimal dependencies

### Why Vanilla JS?
- No build step required
- Fast development
- Easy to understand
- No framework overhead

### Why Proxy APIs?
- Centralized error handling
- Single origin (no CORS issues)
- Environment variable management
- Easier to containerize later

## The "Deployment Problem"

Running this locally requires:
- 3 terminal windows
- 3 Python virtual environments
- Coordinating environment variables
- Ensuring all services start in correct order

**This is the problem containers solve!**

In the next phase, we'll containerize all three services and deploy them to AWS, demonstrating:
- Consistent environments
- Easy scaling
- Simple deployment
- Service orchestration

## License

Part of the YouTube Q&A Dockerless App project.

