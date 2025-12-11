# AI Techne Academy - Processor Container
# Multi-stage build for optimized image size

# =============================================================================
# Stage 1: Builder - Install dependencies
# =============================================================================
FROM python:3.12-slim AS builder

# Set working directory
WORKDIR /build

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies to user directory
# This allows us to copy only the installed packages to the runtime stage
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================================
# Stage 2: Runtime - Create minimal runtime image
# =============================================================================
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY transcription_parser.py .
COPY llm_client.py .
COPY document_generator.py .
COPY main.py .
COPY __init__.py .

# Set Python path to include installed packages
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Add labels for metadata
LABEL maintainer="AI Techne Academy Team"
LABEL version="1.0.0"
LABEL description="Video processing LLM pipeline for document generation"

# Health check (optional, for ECS)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command (can be overridden by ECS task definition)
CMD ["python", "main.py"]