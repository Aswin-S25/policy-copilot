# Slim API image for free-tier hosting (512 MB RAM): no PyTorch. Embeddings
# use the official ONNX export of the same model the database was built with.
# Build from the repository root:  docker build -f deploy/Dockerfile .

# ---- stage 1: fetch the embedding model files (build-time only) ----------------------
FROM python:3.12-slim AS model
RUN pip install --no-cache-dir huggingface_hub==2.4.0
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from huggingface_hub import hf_hub_download as get; \
[get('${EMBEDDING_MODEL}', f, local_dir='/models/embedding') for f in ('onnx/model.onnx', 'tokenizer.json')]" \
 && mv /models/embedding/onnx/model.onnx /models/embedding/model.onnx \
 && rm -rf /models/embedding/onnx /models/embedding/.cache

# ---- stage 2: the API ---------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY deploy/requirements.txt .
RUN pip install -r requirements.txt

ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
COPY --from=model /models/embedding /opt/models/embedding
ENV POLICY_EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    POLICY_EMBEDDING_BACKEND=onnx \
    POLICY_EMBEDDING_ONNX_DIR=/opt/models/embedding \
    POLICY_RATE_LIMIT_BACKEND=memory

COPY alembic.ini .
COPY db ./db
COPY ingest ./ingest
COPY app ./app

# app/main.py creates data/uploads at import. Nothing persistent is stored
# there in deployment: documents live in PostgreSQL, uploads aren't served.
RUN useradd --create-home --uid 10001 appuser     && mkdir -p /app/data/uploads     && chown -R appuser /app/data
USER appuser

# Render (and most hosts) set $PORT. One worker: the LLM concurrency cap and
# the in-memory rate limits are per process. --proxy-headers: rate limits
# per client need the address from the host's proxy, not the proxy's own.
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
