import logging
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import tracelens
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import Settings, get_settings
from database import check_connection, dispose_engine
from routers.chat import chat_router
from routers.conversations import converstation_router
from routers.users import user_router

logger = logging.getLogger("chatjippity")

REQUEST_ID_HEADER = "X-Request-ID"


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # SQL echoing is controlled by DB_ECHO, so keep the engine logger quiet or
    # every statement is logged twice.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup and shutdown.

    Migrations are deliberately NOT run here. Several replicas all calling
    `alembic upgrade head` on boot race for the migration lock; that belongs in a
    one-shot job that completes before the app starts.
    """
    settings = get_settings()

    problems = settings.check_production_safety()
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    logger.info("starting %s (environment=%s)", settings.app_name, settings.environment)

    tracelens.init(service="chatjippity-backend", endpoint=settings.tracelens_ingest_url)

    # Logged, not enforced: the app should still start and report 503 from
    # /health/ready if the database is briefly unavailable.
    if await check_connection():
        logger.info("database connection ok")
    else:
        logger.warning("database unreachable at startup; /health/ready will report degraded")

    try:
        yield
    finally:
        await dispose_engine()
        logger.info("shutdown complete")


def create_app() -> FastAPI:
    """Factory so tests can build an app with overridden settings."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        # Docs off in production: they describe every endpoint to anyone who finds them.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Tag each request with an id and log its duration."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers[REQUEST_ID_HEADER] = request_id

        # Health probes fire constantly; logging them buries everything else.
        if not request.url.path.endswith(("/health", "/health/ready")):
            logger.info(
                "%s %s -> %d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )

        return response

    # The frontend's api/client.ts reads `detail` from every error, accepting a
    # string or a list of validation issues, so all error paths must produce that
    # shape — including unhandled exceptions, which would otherwise return a body
    # the client can't parse.
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        logger.exception("unhandled error (request_id=%s)", request_id)

        # The real message helps locally and leaks internals in production.
        detail = (
            f"{type(exc).__name__}: {exc}"
            if settings.debug
            else "Internal server error. Please try again."
        )
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "request_id": request_id},
        )

    @app.get(f"{settings.api_prefix}/health", tags=["Health"])
    async def health() -> dict[str, str]:
        """Liveness probe — the Dockerfile healthcheck hits this."""
        return {"status": "ok"}

    app.include_router(user_router, prefix=settings.api_prefix)
    app.include_router(converstation_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)

    return app


app = create_app()
