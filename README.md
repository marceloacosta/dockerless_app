# YouTube Q&A App — Build with AWS

A GenAI-powered web application that enables natural language conversations with YouTube video content. Built with AWS serverless services and demonstrates containerization without Docker.

## Vision

This application allows users to submit up to three YouTube URLs, automatically processes their transcripts, and enables Q&A interactions powered by large language models. Users can ask questions about video content and receive grounded answers with citations.

## Architecture

### Frontend
- Static SPA (React/Vue/Svelte) hosted on **Amazon S3 + CloudFront**
- Two simple screens: submit videos and ask questions
- HTTPS communication with backend API

### Backend Services
Two containerized microservices (OCI-compliant, daemonless builds):

1. **Ingestor Service**
   - Fetches YouTube transcripts (`youtube-transcript-api`)
   - Fallback: downloads audio (`yt-dlp`) → transcribes via **Amazon Transcribe**
   - Generates embeddings using **Amazon Bedrock Titan**
   - Stores vectors in **Amazon S3 Vectors**

2. **Q&A API Service**
   - Embeds user queries with **Bedrock Titan**
   - Performs vector similarity search via **S3 Vectors**
   - Generates grounded responses using **Bedrock LLMs** (Claude/Llama)
   - Returns answers with video timestamp citations

### Infrastructure
- **Amazon S3 Vectors** — Vector embeddings storage and similarity search
- **Amazon Bedrock** — LLM and embedding models
- **Amazon SQS** — Ingestion job queue
- **Amazon ECS Fargate** — Managed container runtime (no servers)
- **Amazon ECR** — OCI image registry
- **Amazon CloudWatch** — Logs and metrics

## Prerequisites

- AWS account with access to:
  - Amazon Bedrock (enabled in `us-east-1`)
  - Amazon S3 Vectors
  - Amazon ECS, ECR, SQS
  - CloudFront and S3 for static hosting
- GitHub repository with OIDC configured for AWS
- Build tools:
  - BuildKit or Buildah (for daemonless container builds)
  - `cosign` (optional, for image signing)
  - `syft` (optional, for SBOM generation)

## Repository Structure

```
/frontend/          # SPA application code
/qa-api/            # Q&A service (FastAPI/Flask)
/ingestor/          # YouTube processing service
/iac/               # Infrastructure as Code
README.md           # This file
```

## Containerization Approach

This project builds OCI-compliant container images **without Docker daemon**:
- Uses **BuildKit** (`buildctl`) or **Buildah** for image builds
- Dockerfiles serve as standard recipe format (OCI specification)
- Images pushed directly to Amazon ECR
- Optional image signing with `cosign` (AWS KMS)
- Optional SBOM generation with `syft`

## Security

- **No long-lived credentials** — GitHub OIDC federation for CI/CD
- **Least-privilege IAM** — separate task roles per service
- **Non-root containers** — all images run as unprivileged users
- **Pinned base images** — reproducible builds with digest references

## Deployment

Deployment is automated via GitHub Actions:
1. Build containers with BuildKit
2. Push to Amazon ECR
3. Update ECS Fargate services
4. Deploy frontend to S3 and invalidate CloudFront cache

## License

[LICENSE](LICENSE)
