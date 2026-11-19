FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# CPU-only torch first: the default wheel bundles ~2 GB of CUDA libraries
# the API never uses (embeddings run on CPU; the LLM runs in Ollama).
ARG TORCH_VERSION=2.13.0
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}"

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image: no download at startup, and the
# container works without Hugging Face access.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    POLICY_EMBEDDING_MODEL=${EMBEDDING_MODEL}

COPY alembic.ini .
COPY db ./db
COPY ingest ./ingest
COPY app ./app

# Non-root at runtime. Uploads live on a shared volume mounted here.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser /app/data /opt/hf
USER appuser

EXPOSE 8000

# One process: the LLM concurrency cap is per process (item 5).
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
