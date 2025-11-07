# Building Containers By Hand: A Deep Dive into OCI

> **Understanding containers from first principles by building them manually—no Docker required.**

This repository demonstrates how to build production-ready OCI (Open Container Initiative) containers completely by hand, without using Docker. It's an educational journey into container internals that resulted in a fully functional, deployed application on AWS ECS.

## What This Project Teaches

- **Container internals**: What's actually inside a container image (layers, config, manifest)
- **OCI specifications**: Image spec, runtime spec, distribution spec
- **Manual building**: Creating containers using only `curl`, `tar`, `jq`, and `shasum`
- **Real debugging**: Platform mismatches, Python version conflicts, PATH issues
- **Production deployment**: Running hand-built containers on AWS ECS with ALB

## The Application

A YouTube Q&A system with three microservices:

```
┌──────────────┐
│  Frontend    │  Flask web interface
│  (Port 5000) │  Submit videos, ask questions
└──────┬───────┘
       │
       ├─────► [SQS Queue] ─────► ┌──────────────┐
       │                          │   Ingestor   │  Fetches transcripts
       │                          │              │  Uploads to S3
       │                          └──────┬───────┘
       │                                 │
       │                                 ▼
       │                          [Bedrock Knowledge Base]
       │                                 ▲
       │                                 │
       └─────► ┌──────────────┐         │
               │    QA API    │─────────┘
               │  (Port 8000) │  RAG-powered Q&A
               └──────────────┘
```

### Services

**Frontend** (`frontend/`)
- Flask web app serving static HTML/CSS/JS
- Submits YouTube URLs to SQS
- Queries QA API for answers

**Ingestor** (`ingestor/`)
- Polls SQS for YouTube URLs
- Fetches transcripts using `youtube-transcript-api`
- Uploads to S3 and syncs with Bedrock Knowledge Base
- **Note**: YouTube blocks cloud provider IPs (see [Troubleshooting](#troubleshooting))

**QA API** (`qa_api/`)
- FastAPI REST API
- Uses AWS Bedrock Knowledge Base for RAG (Retrieval-Augmented Generation)
- Returns AI-generated answers with sources

## Quick Start

### Prerequisites

- Python 3.11
- AWS account with Bedrock access
- AWS CLI configured
- `jq`, `skopeo` (for OCI image building)

### Local Development

```bash
# 1. Set up Bedrock Knowledge Base (one-time)
# - Create S3 bucket for transcripts
# - Create Bedrock Knowledge Base pointing to that bucket
# - Note the KB_ID and DATA_SOURCE_ID

# 2. Set environment variables
export AWS_REGION=us-east-1
export KB_ID=your-knowledge-base-id
export KB_DATA_SOURCE_ID=your-data-source-id
export KB_BUCKET=your-s3-bucket
export SQS_QUEUE_URL=your-sqs-queue-url
export BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0

# 3. Run services (in separate terminals)
cd ingestor && pip install -r requirements.txt && python app.py
cd qa_api && pip install -r requirements.txt && uvicorn app:app --port 8000
cd frontend && pip install -r requirements.txt && flask run --port 5000
```

## Building Containers By Hand

The core learning experience is in `manual-oci-build/`. This directory contains scripts and documentation for building OCI images without Docker.

### The Manual Build Process

#### 1. Get Base Layers

Download Python base image layers from Docker Hub:

```bash
# Authenticate to Docker Hub
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull" | jq -r .token)

# Get manifest
curl -H "Authorization: Bearer $TOKEN" \
  "https://registry-1.docker.io/v2/library/python/manifests/3.11-slim" \
  > manifest.json

# Download each layer
for digest in $(jq -r '.layers[].digest' manifest.json); do
  curl -L -H "Authorization: Bearer $TOKEN" \
    "https://registry-1.docker.io/v2/library/python/blobs/$digest" \
    -o "layer-${digest#sha256:}.tar.gz"
done
```

#### 2. Create Application Layers

```bash
# Install dependencies for target platform
pip3 install \
  --target layer5/usr/local/lib/python3.11/site-packages \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --only-binary=:all: \
  --no-cache-dir \
  fastapi uvicorn boto3 pydantic

# Package as tar.gz
cd layer5 && tar -czf ../layer5.tar.gz . && cd ..
```

#### 3. Write OCI Config

`config.json` defines the container's runtime configuration:

```json
{
  "architecture": "amd64",
  "os": "linux",
  "config": {
    "Env": ["PATH=/usr/local/bin:/usr/bin", "PYTHONUNBUFFERED=1"],
    "Cmd": ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0"],
    "WorkingDir": "/app",
    "ExposedPorts": {"8000/tcp": {}}
  },
  "rootfs": {
    "type": "layers",
    "diff_ids": [
      "sha256:abc123...",  // Uncompressed layer digests
      "sha256:def456..."
    ]
  }
}
```

#### 4. Write OCI Manifest

`manifest.json` links everything together:

```json
{
  "schemaVersion": 2,
  "config": {
    "digest": "sha256:config-hash...",
    "size": 2048
  },
  "layers": [
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "digest": "sha256:layer-hash...",  // Compressed layer digest
      "size": 29778104
    }
  ]
}
```

#### 5. Assemble OCI Layout

```bash
mkdir -p oci-image/blobs/sha256

# Copy all blobs (layers, config, manifest) using digests as filenames
cp config.json oci-image/blobs/sha256/$(shasum -a 256 config.json | cut -d' ' -f1)
cp layer1.tar.gz oci-image/blobs/sha256/$(shasum -a 256 layer1.tar.gz | cut -d' ' -f1)
# ... repeat for all layers

# Create OCI layout marker
echo '{"imageLayoutVersion":"1.0.0"}' > oci-image/oci-layout

# Create index.json (entry point)
cat > oci-image/index.json <<EOF
{
  "schemaVersion": 2,
  "manifests": [{
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "digest": "sha256:manifest-hash...",
    "size": 1234,
    "annotations": {"org.opencontainers.image.ref.name": "myapp:latest"}
  }]
}
EOF
```

#### 6. Push to Registry

```bash
# Push to AWS ECR (or any OCI-compatible registry)
aws ecr get-login-password | skopeo login --username AWS --password-stdin ecr-url
skopeo copy oci:oci-image/ docker://your-ecr-url/myapp:latest
```

### Key Learnings from Manual Building

#### Bug #1: uvicorn PATH Issue
- **Problem**: `pip install --target` doesn't add executables to PATH
- **Fix**: Use `python -m uvicorn` instead of `uvicorn` directly

#### Bug #2: Platform Mismatch
- **Problem**: Built on macOS, running on Linux—C extensions are platform-specific
- **Fix**: Use `pip install --platform manylinux2014_x86_64`

#### Bug #3: Python Version Mismatch
- **Problem**: Local Python 3.13, container has Python 3.11
- **Fix**: Add `--python-version 3.11` to pip install

## AWS Deployment

### Architecture

```
Internet → [ALB] → Frontend (ECS Fargate)
            ↓
           QA API (ECS Fargate) ← Bedrock KB
            
[SQS] → Ingestor (ECS Fargate) → S3 → Bedrock KB
```

### Deploy to AWS ECS

1. **Create ECR Repositories**:
```bash
aws ecr create-repository --repository-name frontend
aws ecr create-repository --repository-name qa-api
aws ecr create-repository --repository-name ingestor
```

2. **Push Images** (using manually built OCI images):
```bash
skopeo copy oci:frontend-image/ docker://YOUR_ECR_URL/frontend:latest
skopeo copy oci:qa-api-image/ docker://YOUR_ECR_URL/qa-api:latest
skopeo copy oci:ingestor-image/ docker://YOUR_ECR_URL/ingestor:latest
```

3. **Create ECS Cluster**:
```bash
aws ecs create-cluster --cluster-name youtube-qa
```

4. **Deploy Services** (see `manual-oci-build/` for task definitions)

### Required IAM Permissions

The ECS task execution role needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:RetrieveAndGenerate",
        "bedrock:Retrieve",
        "bedrock:InvokeModel",
        "bedrock:StartIngestionJob"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR-BUCKET",
        "arn:aws:s3:::YOUR-BUCKET/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage"
      ],
      "Resource": "arn:aws:sqs:REGION:ACCOUNT:QUEUE-NAME"
    }
  ]
}
```

## Troubleshooting

### YouTube IP Blocking

**Problem**: YouTube blocks transcript API requests from cloud provider IPs (AWS, GCP, Azure).

**Symptoms**:
```
TooManyRequests: You have done too many requests and your IP has been blocked
You are doing requests from an IP belonging to a cloud provider
```

**Solutions**:
1. **Use proxies** (recommended for production):
   ```python
   proxies = {'http': 'http://proxy.example.com:8080'}
   transcript = YouTubeTranscriptApi.get_transcript(video_id, proxies=proxies)
   ```

2. **Run Ingestor outside AWS**: On a local machine or non-cloud server

3. **Use YouTube Data API v3**: Requires API key, has quotas

### Container Debugging

Check logs:
```bash
aws logs tail /ecs/SERVICE-NAME --follow
```

Common issues:
- Missing environment variables
- IAM permission errors
- Network configuration
- Image platform mismatch

## What You'll Learn

1. **Container Internals**
   - Layers are just tar files
   - Config and manifest are JSON
   - Digests are SHA256 hashes
   - Images are stored as content-addressable blobs

2. **OCI Specifications**
   - Image Spec: How to package
   - Runtime Spec: How to run
   - Distribution Spec: How to share

3. **Real-World Issues**
   - Platform compatibility (macOS vs Linux)
   - Python version matching
   - Executable PATH configuration
   - External service limitations

4. **Production Deployment**
   - Container registries (ECR)
   - Container orchestration (ECS)
   - Load balancing (ALB)
   - IAM permissions
   - Logging and monitoring

## Educational Value

**Why build containers by hand?**

- **Deep understanding**: Know exactly what Docker automates
- **Debugging superpowers**: Fix issues others can't understand
- **Platform expertise**: Handle cross-compilation correctly
- **Optimization knowledge**: Make informed decisions about layers and caching
- **Tool independence**: Use buildah, kaniko, img, or build your own

**When abstractions leak** (and they will), this knowledge becomes invaluable.

## Resources

### OCI Specifications
- [OCI Image Specification](https://github.com/opencontainers/image-spec)
- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec)
- [OCI Distribution Specification](https://github.com/opencontainers/distribution-spec)

### Tools Used
- [skopeo](https://github.com/containers/skopeo) - Manipulate container images
- [jq](https://stedolan.github.io/jq/) - JSON processor
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) - Fetch YouTube transcripts

### AWS Services
- [AWS Bedrock](https://aws.amazon.com/bedrock/) - Managed AI/ML service
- [AWS ECS Fargate](https://aws.amazon.com/fargate/) - Serverless containers
- [AWS ECR](https://aws.amazon.com/ecr/) - Container registry

## License

MIT License - Feel free to use this for learning and teaching!

## Acknowledgments

Inspired by:
- Julia Evans' zines on debugging and systems
- Jessie Frazelle's container security work
- Kelsey Hightower's "Kubernetes the Hard Way"

---

**Built with curiosity, debugged with patience, deployed with confidence.**

_"Any sufficiently advanced technology is indistinguishable from magic... until you understand how it works."_
