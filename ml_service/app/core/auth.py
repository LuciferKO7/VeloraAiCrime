"""
Service-to-service authentication middleware and dependencies.
Adheres to MASTER_PROMPT.md §6.3:
'Service-to-service: header X-Service-Key: $SERVICE_KEY'
"""

import secrets
from typing import Optional
from fastapi import Header, Request
from ml_service.app.core.config import settings
from ml_service.app.core.errors import AuthInvalidError


async def verify_service_key(
    x_service_key: Optional[str] = Header(None, alias="X-Service-Key")
) -> str:
    """FastAPI dependency that validates the X-Service-Key header."""
    if not x_service_key:
        raise AuthInvalidError(message="Missing required header: X-Service-Key")

    # If configured key is empty, reject to prevent accidental bypass
    if not settings.SERVICE_KEY:
        raise AuthInvalidError(message="Service key not configured on ML service")

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(x_service_key, settings.SERVICE_KEY):
        raise AuthInvalidError(message="Invalid service key provided")

    return x_service_key
