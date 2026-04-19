FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# git is required at runtime: services/file_writer.py auto-commits every
# successful mediated write to the PKA repo as an insurance snapshot.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl \
 && rm -rf /var/lib/apt/lists/*

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
