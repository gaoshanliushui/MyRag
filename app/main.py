"""
FastAPI Application Entry Point

Main application with middleware, startup/shutdown hooks,
and API router registration.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest

from app.config import settings
from app.core.monitoring.metrics import setup_metrics
from app.db.session import check_db_connection, close_db, init_db
from app.utils.exceptions import APIError, MyRagException
from app.utils.logging import RequestLogContext, get_logger, request_id_var

logger = get_logger("myrag.main")

# Prometheus metrics
REQUEST_COUNT = Counter(
    "myrag_requests_total",
    "Total request count",
    ["method", "endpoint", "tenant_id", "status"]
)
REQUEST_LATENCY = Histogram(
    "myrag_request_latency_seconds",
    "Request latency",
    ["method", "endpoint", "tenant_id"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Check database connection
    if await check_db_connection():
        logger.info("Database connection verified")
    else:
        logger.warning("Database connection check failed")

    # Setup Prometheus metrics
    if settings.METRICS_ENABLED:
        setup_metrics()
        logger.info("Metrics enabled")

    # Initialize embedding service (lazy loading on first use)
    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await close_db()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="分布式多租户混合检索企业级RAG系统",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging and metrics middleware
    @app.middleware("http")
    async def request_middleware(request: Request, call_next: Any) -> Response:
        # Generate request ID
        request_id = request.headers.get("X-Request-ID", "")
        if not request_id:
            import uuid
            request_id = str(uuid.uuid4())[:8]

        # Get tenant ID from header or API key (to be validated by auth)
        tenant_id = request.headers.get("X-Tenant-ID", "")

        # Set logging context
        with RequestLogContext(request_id, tenant_id):
            start_time = time.time()

            # Log request
            logger.debug(
                f"Request started: {request.method} {request.url.path}",
                extra={"tenant_id": tenant_id}
            )

            try:
                response = await call_next(request)

                # Calculate latency
                latency = time.time() - start_time

                # Record metrics
                endpoint = request.url.path
                status = response.status_code

                REQUEST_COUNT.labels(
                    method=request.method,
                    endpoint=endpoint,
                    tenant_id=tenant_id or "anonymous",
                    status=status
                ).inc()

                REQUEST_LATENCY.labels(
                    method=request.method,
                    endpoint=endpoint,
                    tenant_id=tenant_id or "anonymous"
                ).observe(latency)

                # Add request ID to response headers
                response.headers["X-Request-ID"] = request_id

                logger.debug(
                    f"Request completed: {request.method} {endpoint} "
                    f"-> {status} ({latency:.3f}s)",
                    extra={"tenant_id": tenant_id, "latency": latency}
                )

                return response

            except Exception as e:
                latency = time.time() - start_time
                logger.exception(
                    f"Request failed: {request.method} {request.url.path} "
                    f"({latency:.3f}s)",
                    extra={"tenant_id": tenant_id}
                )
                raise

    # Exception handlers
    @app.exception_handler(MyRagException)
    async def myrag_exception_handler(request: Request, exc: MyRagException) -> JSONResponse:
        """Handle MyRag exceptions."""
        logger.error(f"MyRag exception: {exc}", extra={"request_id": request_id_var.get()})

        status_code = 500
        error_code = "INTERNAL_ERROR"

        if isinstance(exc, APIError):
            status_code = exc.status_code
            error_code = exc.error_code

        return JSONResponse(
            status_code=status_code,
            content={
                "error": exc.message,
                "error_code": error_code,
                "details": exc.details,
                "request_id": request_id_var.get(),
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception(f"Unexpected exception: {exc}")

        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "details": {"type": type(exc).__name__},
                "request_id": request_id_var.get(),
            }
        )

    # Health check endpoint (root level)
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Basic health check."""
        db_ok = await check_db_connection()
        return {
            "status": "healthy" if db_ok else "degraded",
            "version": settings.APP_VERSION,
            "services": {
                "database": "ok" if db_ok else "error",
            }
        }

    # Prometheus metrics endpoint
    @app.get("/metrics", tags=["Monitoring"])
    async def metrics_endpoint() -> Response:
        """Prometheus metrics."""
        if not settings.METRICS_ENABLED:
            return JSONResponse(
                status_code=404,
                content={"error": "Metrics disabled"}
            )
        return Response(
            content=generate_latest(),
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )

    # Register API routers
    from app.api.v1.router import api_router
    app.include_router(api_router, prefix=settings.API_PREFIX)

    return app


# Create application instance
app = create_app()


def main() -> None:
    """Entry point for running the application."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )


if __name__ == "__main__":
    main()