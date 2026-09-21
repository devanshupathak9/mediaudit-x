# Backend dev image: pinned to Python 3.12 because the pinned deps
# (pydantic 2.9) have no wheels for 3.14.
FROM python:3.12-slim

# Tesseract OCR binary: app/ocr/extract.py's pytesseract fallback shells
# out to this executable. It is not a pip package -- pip install alone
# never provides it (see README.md "Known limitations").
RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    # Slow connections: wait longer per read and retry instead of failing.
    PIP_DEFAULT_TIMEOUT=300 PIP_RETRIES=10 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
# The cache mount keeps downloaded packages between builds, so a build
# that fails halfway doesn't re-download everything on the next try.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
