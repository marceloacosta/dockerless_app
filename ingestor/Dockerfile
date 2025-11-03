# Dockerfile for Ingestor Service (OCI Recipe)
# This file serves as a recipe; we'll build with BuildKit, not docker daemon

FROM python:3.11-slim

# Install system dependencies for audio processing (yt-dlp fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Switch to non-root user
USER appuser

# Run the application
CMD ["python", "-u", "app.py"]

