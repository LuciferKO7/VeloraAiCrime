import re
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ERROR_STATUS_MAP: dict[str, int] = {
    "AUTH_INVALID": 401,
    "AUTH_EXPIRED": 401,
    "ACCOUNT_LOCKED": 423,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "PURPOSE_REQUIRED": 400,
    "CONFLICT_VERSION": 409,
    "RATE_LIMITED": 429,
    "ML_BUSY": 429,
    "LLM_UNAVAILABLE": 503,
    "LLM_UNAVAILABLE_LOCAL": 503,
    "ML_UNAVAILABLE": 503,
    "SPEECH_UNAVAILABLE": 503,
    "LLM_SCHEMA_INVALID": 502,
    "INTERNAL": 500,
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code or ERROR_STATUS_MAP.get(code, 500)
        super().__init__(self.message)


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    status_code = ERROR_STATUS_MAP.get(code, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    if exc.code == "FORBIDDEN" or exc.status_code == 403:
        if not getattr(request.state, "access_denied_logged", False):
            case_match = re.search(r"/cases/([^/?#]+)", request.url.path)
            if case_match:
                case_id = case_match.group(1)
                user = getattr(request.state, "user", {}) or {}
                purpose = request.headers.get("x-access-purpose")
                client_ip = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
                request.state.access_denied_logged = True
                try:
                    from backend.app.audit.chain import write_audit_entry
                    write_audit_entry(
                        action="access.denied",
                        user_id=user.get("id"),
                        username=user.get("username"),
                        role=user.get("role"),
                        resource_type="case",
                        resource_id=case_id,
                        case_id=case_id,
                        purpose=purpose,
                        ip=client_ip,
                        user_agent=user_agent,
                        status_code=403,
                        details={"reason": exc.message, "path": request.url.path, "method": request.method},
                    )
                except Exception:
                    pass
    return error_response(code=exc.code, message=exc.message, details=exc.details)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": exc.errors()},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Reverse map status_code to code if not provided
    code = "INTERNAL"
    for c, sc in ERROR_STATUS_MAP.items():
        if sc == exc.status_code:
            code = c
            break
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "AUTH_INVALID"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "FORBIDDEN"
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"

    return error_response(
        code=code,
        message=str(exc.detail) if exc.detail else "HTTP Exception",
        details={},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        code="INTERNAL",
        message="Internal server error",
        details={"error_type": type(exc).__name__},
    )
