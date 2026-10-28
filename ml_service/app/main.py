"""
Velora ML Service entrypoint.
Adheres to MASTER_PROMPT.md:
- Microservice port: 8001
- Base path prefix: /ml/v1
- Service auth: X-Service-Key
- Standard error contract (§6.3)
"""

import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from ml_service.app.core.config import settings
from ml_service.app.core.errors import (
    MLError,
    generic_http_error_handler,
    ml_error_handler,
    validation_error_handler,
)
from ml_service.app.models.manager import model_manager
from ml_service.app.routers import health

# Configure structured logging per MASTER_PROMPT.md §0 R14 (no raw print)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("velora.ml_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for service startup and shutdown."""
    logger.info("Velora ML Service starting up on port %d...", settings.PORT)
    logger.info("Configuration: %s", repr(settings))
    mem_status = model_manager.get_memory_status()
    logger.info(
        "Hardware: CUDA=%s, Device=%s, GPU='%s', VRAM Total=%.1f MiB, Low-VRAM=%s",
        mem_status["cuda_available"],
        mem_status["device"],
        mem_status["gpu_name"] or "N/A",
        mem_status["vram_total_mb"],
        mem_status["low_vram_mode"],
    )

    yield

    logger.info("Velora ML Service shutting down, releasing VRAM...")
    model_manager.unload_active_model()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Velora ML Service",
    description="FastAPI service for suspect composite synthesis and incident reconstruction sketches.",
    version="1.0.0",
    lifespan=lifespan,
)

from starlette.exceptions import HTTPException as StarletteHTTPException

# Register custom exception handlers conforming to §6.3
app.add_exception_handler(MLError, ml_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(HTTPException, generic_http_error_handler)
app.add_exception_handler(StarletteHTTPException, generic_http_error_handler)

# Include API routers under /ml/v1
app.include_router(health.router, prefix="/ml/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ml_service.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
