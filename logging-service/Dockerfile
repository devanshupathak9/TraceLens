# Built with the REPO ROOT as context (see docker-compose.yml), because bus.py
# imports ../lambda:
#   docker build -f logging-service/Dockerfile .

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Copied first so the dependency layer caches independently of source changes.
COPY logging-service/requirements.txt .
RUN pip install -r requirements.txt

# bus.py resolves the lambda folder as ../lambda relative to itself (/app),
# so it lands at /lambda.
COPY --chown=appuser:appuser lambda /lambda
COPY --chown=appuser:appuser logging-service/ .

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8001/health || exit 1

# Binds :: rather than 0.0.0.0 because this service is only ever reached over a
# private network, and Railway's is IPv6-only — an IPv4-only listener is simply
# unreachable there, and the SDK swallows the connection error, so events would
# vanish with nothing in any log. The socket is dual-stack, so IPv4 callers
# (compose, the healthcheck below) still work.
CMD ["uvicorn", "main:app", "--host", "::", "--port", "8001"]
