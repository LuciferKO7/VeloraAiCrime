import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.config import settings
from backend.app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from backend.app.core.logging import logger
from backend.app.routers.auth import limiter


def discover_routers(app: FastAPI, prefix: str = "/api/v1"):
    import backend.app.routers as routers_pkg

    for _, module_name, _ in pkgutil.iter_modules(routers_pkg.__path__):
        full_name = f"backend.app.routers.{module_name}"
        mod = importlib.import_module(full_name)
        if hasattr(mod, "router"):
            r = mod.router
            app.include_router(r, prefix=prefix)
            logger.info(f"Registered router from {module_name}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: validate secrets fail-fast
    settings.validate_secrets()
    logger.info("Configuration validated and backend hub initialized")
    try:
        from backend.app.services.gallery_service import gallery_index

        gallery_index.load_from_db()
        logger.info("Gallery embedding matrix initialized: %d faces loaded", len(gallery_index))
    except Exception as exc:
        logger.warning("Could not initialize gallery embedding matrix on startup: %s", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="VELORA Hub API",
        version="1.1",
        lifespan=lifespan,
    )

    # Rate limiting state
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom Exception Handlers per §6.3
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Auto-discover routers in app/routers/
    discover_routers(app)

    return app


app = create_app()
