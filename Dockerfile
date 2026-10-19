# Lightweight Python 3.12 Dockerfile tailored for 512 MB RAM free hosting (Render / Hugging Face Spaces)
FROM python:3.12-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight backend dependencies (FastEmbed ONNX, no PyTorch, no Transformers)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download FastEmbed ONNX model at build time to prevent runtime cold start download (Task 11)
RUN python -c "from fastembed import TextEmbedding; list(TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2').embed(['warmup']))"


# Copy backend application and prebuilt knowledge index
COPY backend/ ./backend/
COPY data/ ./data/

# Default deployment configuration
ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    VECTOR_DB_TYPE=local \
    ENABLE_HF_LOCAL=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
