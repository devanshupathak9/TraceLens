# Built with the REPO ROOT as context (see docker-compose.yml), because the
# image needs ../sdk for the editable tracelens install:
#   docker build -f backend/Dockerfile .

# --- build ---------------------------------------------------------------
FROM python:3.13-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# requirements.txt says `-e ../sdk`, resolved relative to the workdir /app.
COPY sdk /sdk
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# --- runtime -------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# curl is used by the healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root: a container that doesn't need to write to its own filesystem
# shouldn't be able to.
RUN useradd --create-home --uid 1000 appuser

COPY --from=build /opt/venv /opt/venv
# The editable install points at /sdk, so it must exist at runtime too.
COPY --from=build /sdk /sdk

WORKDIR /app
COPY --chown=appuser:appuser backend/ .

USER appuser

EXPOSE 8000

# Hits liveness, not readiness: a database outage shouldn't make Docker restart
# a process that is working correctly.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# One worker per container. Scale with replicas rather than --workers: the
# app is async and IO-bound, and multiple workers in one container make CPU
# and memory limits much harder to reason about.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
