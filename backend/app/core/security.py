from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from backend.app.core.config import settings
from backend.app.core.errors import AppError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(sub: str, role: str, expires_minutes: int | None = None) -> str:
    exp_delta = timedelta(minutes=expires_minutes if expires_minutes is not None else settings.JWT_EXPIRE_MINUTES)
    expire = datetime.now(UTC) + exp_delta
    payload = {
        "sub": sub,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise AppError("AUTH_EXPIRED", "Token has expired") from None
    except jwt.InvalidTokenError:
        raise AppError("AUTH_INVALID", "Invalid token") from None
