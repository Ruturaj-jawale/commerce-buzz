# Production Dockerfile for SaaS MCP FastAPI Backend + Ingestion Worker
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    # Required by pdf2image (PDF -> image conversion for OCR)
    poppler-utils \
    # Required by pytesseract (OCR engine)
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# --workers 1: in-process ingestion worker runs per-process; keep at 1 for Phase 1.
# Scale horizontally with multiple containers instead of multiple workers per container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
