# Build from the REPO ROOT, exactly like backend/Dockerfile — on Railway/Render
# set only the Dockerfile path (logging-service/Dockerfile) and leave the root
# directory empty:
#   docker build -f logging-service/Dockerfile .

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copied first so the dependency layer caches independently of source changes.
COPY logging-service/requirements.txt .
RUN pip install -r requirements.txt

COPY logging-service/ .

EXPOSE 8001

# Listen on the port the platform injects; 8001 for compose and local runs.
#
# 0.0.0.0, not ::. The IPv6 bind was for Railway's private network, but uvicorn
# opens it v6-only: 127.0.0.1 is refused, so the public proxy and Docker port
# publishing both fail against it. This service is reached over its public URL,
# which is IPv4, so bind IPv4. (Going back to private networking means :: — and
# then only IPv6 callers work.)
#
# exec keeps uvicorn in PID 1's place so it still receives SIGTERM on shutdown.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}"]
