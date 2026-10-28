"""
Standard error definitions and exception handlers for Velora ML Service.
Adheres strictly to MASTER_PROMPT.md §6.3 error format:
{"error": {"code": "STRING", "message": "human readable", "details": {}}}
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class MLError(HTTPException):
    """Base application exception for ML service errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details or {}


class AuthInvalidError(MLError):
    """Raised when service-to-service authentication fails."""

    def __init__(self, message: str = "Invalid or missing X-Service-Key header", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="AUTH_INVALID",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class MLUnavailableError(MLError):
    """Raised when ML pipeline/device is not ready or failed to load."""

    def __init__(self, message: str = "ML pipeline is currently unavailable", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="ML_UNAVAILABLE",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class MLBusyError(MLError):
    """Raised when GPU inference queue is full or device is occupied."""

    def __init__(self, message: str = "ML service is currently busy processing another request", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="ML_BUSY",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


def format_error_response(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Helper to produce standard error payload."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


async def ml_error_handler(request: Request, exc: MLError) -> JSONResponse:
    """Handler for explicit MLError exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(exc.code, exc.message, exc.details),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler for FastAPI request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=format_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": exc.errors()},
        ),
    )


async def generic_http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler for generic FastAPI HTTPExceptions."""
    code_map = {
        status.HTTP_401_UNAUTHORIZED: "AUTH_INVALID",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_503_SERVICE_UNAVAILABLE: "ML_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "INTERNAL")
    message = str(exc.detail) if exc.detail else "An internal error occurred"
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(code=code, message=message),
    )
