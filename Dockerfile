# Get Well OCR: container image with the OCR API (default) and the Streamlit app.
#
# Build:   docker build -t get-well-ocr .
# API:     docker run -p 8000:8000 --env-file .env get-well-ocr
# App:     docker run -p 8501:8501 --env-file .env get-well-ocr \
#            streamlit run app.py --server.port 8501 --server.address 0.0.0.0

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Tesseract's own threads only slow things down in a container; parallelise with workers instead
    OMP_THREAD_LIMIT=1 \
    OCR_ENGINE=tesseract

# System programs: Tesseract with German + English, libdmtx for the medication plan barcode,
# glib for OpenCV
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
        libdmtx0b libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code changes don't reinstall everything
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as a normal user; it may only write where the pipeline stores files
RUN useradd --create-home --uid 1000 app \
 && mkdir -p data/private cache outputs \
 && chown -R app:app data cache outputs
USER app

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)" || exit 1

# Number of API processes: set WEB_CONCURRENCY (uvicorn reads it), default 1
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
