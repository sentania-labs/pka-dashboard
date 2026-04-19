FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8443

# Production: HTTPS on 8443 with certs bind-mounted at /certs/ by Navani.
# For local dev / HTTP testing, override CMD:
#   docker run ... pka-dashboard uvicorn app.main:app --host 0.0.0.0 --port 8000
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8443", \
     "--ssl-keyfile", "/certs/tls.key", \
     "--ssl-certfile", "/certs/tls.crt"]
