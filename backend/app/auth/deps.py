from collections.abc import Callable

from fastapi import Depends, Header
from fastapi import Path as FastApiPath
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.core.errors import AppError
from backend.app.core.security import decode_access_token
from backend.app.db.session import get_connection


def get_token_from_header(authorization: str | None = Header(None)) -> str:
    if not authorization:
        raise AppError("AUTH_INVALID", "Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppError("AUTH_INVALID", "Invalid Authorization header format")
    return parts[1]


def get_current_user(
    token: str = Depends(get_token_from_header),
    conn: Connection = Depends(get_connection),
) -> dict:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AppError("AUTH_INVALID", "Invalid token subject")

    row = conn.execute(
        text("SELECT id, username, full_name, role, is_active, failed_logins, locked_until FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().fetchone()

    if not row:
        raise AppError("AUTH_INVALID", "User not found")
    if not row["is_active"]:
        raise AppError("AUTH_INVALID", "User account is disabled")

    return dict(row)


def require_role(*allowed_roles: str) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise AppError("FORBIDDEN", f"Role '{user['role']}' is not authorized for this operation")
        return user
    return dependency


def require_access_purpose(x_access_purpose: str | None = Header(None)) -> str:
    if not x_access_purpose or len(x_access_purpose.strip()) < 5:
        raise AppError("PURPOSE_REQUIRED", "Header X-Access-Purpose with minimum 5 characters is required")
    return x_access_purpose.strip()


def require_case_access(level: str = "view") -> Callable:
    """
    Implements §6.3 Role matrix for case access:
    - investigator/artist -> only cases with non-revoked case_access row
      (edit for mutations, view for reads)
    - supervisor -> all cases
    - auditor -> case metadata but no case content (sessions/images/statements)
    - admin -> no case content unless granted access
    """
    def dependency(
        case_id: str = FastApiPath(...),
        user: dict = Depends(get_current_user),
        purpose: str = Depends(require_access_purpose),
        conn: Connection = Depends(get_connection),
    ) -> dict:
        role = user["role"]
        user_id = user["id"]

        # Check case exists
        case_row = conn.execute(
            text("SELECT id, case_number, title, status FROM cases WHERE id = :id"),
            {"id": case_id},
        ).mappings().fetchone()
        if not case_row:
            raise AppError("NOT_FOUND", "Case not found")

        if role == "supervisor":
            return {"case": dict(case_row), "user": user, "purpose": purpose}

        if role == "auditor":
            # Auditor can view case metadata only
            if level != "view":
                raise AppError("FORBIDDEN", "Auditors cannot mutate cases")
            return {"case": dict(case_row), "user": user, "purpose": purpose}

        if role in ("investigator", "artist", "admin"):
            access_row = conn.execute(
                text(
                    """
                    SELECT access_level, revoked_at
                    FROM case_access
                    WHERE case_id = :case_id AND user_id = :user_id AND revoked_at IS NULL
                    """
                ),
                {"case_id": case_id, "user_id": user_id},
            ).mappings().fetchone()

            if not access_row:
                raise AppError("FORBIDDEN", "Access to this case has not been granted or was revoked")

            granted_level = access_row["access_level"]
            if level == "edit" and granted_level != "edit":
                raise AppError("FORBIDDEN", "Edit permission required for this operation")

            return {"case": dict(case_row), "user": user, "purpose": purpose}

        raise AppError("FORBIDDEN", "Unauthorized role for case access")

    return dependency
