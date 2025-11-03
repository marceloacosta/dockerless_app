# Ingestor Service

YouTube transcript processing and embedding generation service.

## Purpose

The ingestor service processes YouTube URLs submitted by users:

1. **Fetch Transcripts**: Retrieves transcripts using `youtube-transcript-api`
2. **Fallback to Audio**: If transcript unavailable, downloads audio with `yt-dlp` and transcribes using Amazon Transcribe
3. **Text Chunking**: Splits transcript into ~1000 token segments with 200 token overlap
4. **Embedding Generation**: Creates vector embeddings using Amazon Bedrock Titan
5. **Vector Storage**: Writes vectors and metadata to Amazon S3 Vectors

## Architecture

- **Triggered by**: SQS messages containing YouTube URLs and collection IDs
- **Processing**: Long-running worker that polls SQS continuously
- **Output**: Vectors stored in S3 Vectors with metadata (video_id, timestamps, text)

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-east-1` |
| `SQS_QUEUE_URL` | SQS queue URL for ingestion jobs | *required* |
| `BEDROCK_EMBED_MODEL` | Bedrock embedding model ID | `amazon.titan-embed-text-v1` |
| `S3_VECTORS_BUCKET` | S3 bucket for vector storage | *required* |
| `S3_VECTORS_INDEX` | Vector index name | *required* |

## IAM Permissions Required

```json
{
  "Effect": "Allow",
  "Action": [
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:GetQueueAttributes",
    "bedrock:InvokeModel",
    "s3:PutObject",
    "s3:GetObject",
    "transcribe:StartTranscriptionJob",
    "transcribe:GetTranscriptionJob"
  ],
  "Resource": [...]
}
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/.../ingestion-jobs"
export S3_VECTORS_BUCKET="bwaws-vectors"
export S3_VECTORS_INDEX="videos-index"

# Run locally
python app.py
```

## Container Build

Build OCI image using BuildKit (no Docker daemon):

```bash
# Using buildctl directly
buildctl build \
  --frontend dockerfile.v0 \
  --local context=. \
  --local dockerfile=. \
  --output type=image,name=ingestor:latest,push=false
```

Or with docker buildx (uses BuildKit):

```bash
docker buildx build -t ingestor:latest .
```

## Deployment

Runs on **Amazon ECS Fargate** with:
- Non-root user (`appuser`)
- Read-only root filesystem (where possible)
- Minimum IAM permissions
- CloudWatch logs integration

## Dependencies

- **boto3**: AWS SDK for Python
- **youtube-transcript-api**: Fetch YouTube transcripts
- **yt-dlp**: Download audio for fallback transcription
- **tiktoken**: Token counting for text chunking
- **ffmpeg**: Audio processing (system dependency)

