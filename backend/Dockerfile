# --- build ---------------------------------------------------------------
# Dependencies are installed into a virtualenv in a builder stage so the final
# image carries no compilers or build headers.
FROM python:3.13-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied on its own so the dependency layer is cached independently of source.
COPY requirements.txt .
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

WORKDIR /app
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Hits liveness, not readiness: a database outage shouldn't make Docker restart
# a process that is working correctly.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# One worker per container. Scale with replicas rather than --workers: the
# streaming endpoint is async and IO-bound, and multiple workers in one container
# make CPU and memory limits much harder to reason about.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
