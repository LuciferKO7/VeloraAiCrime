from collections.abc import Callable

from fastapi import Depends, Header, Request
from fastapi import Path as FastApiPath
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.core.errors import AppError
from backend.app.core.security import decode_access_token
from backend.app.db.session import get_connection


def _log_access_denied(
    user: dict,
    case_id: str,
    purpose: str | None,
    request: Request,
    reason: str,
    conn: Connection | None = None,
) -> None:
    if getattr(request.state, "access_denied_logged", False):
        return
    request.state.access_denied_logged = True
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        write_audit_entry(
            conn,
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
            details={"reason": reason, "path": request.url.path, "method": request.method},
        )
    except Exception:
        pass


def get_token_from_header(authorization: str | None = Header(None)) -> str:
    if not authorization:
        raise AppError("AUTH_INVALID", "Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppError("AUTH_INVALID", "Invalid Authorization header format")
    return parts[1]


def get_current_user(
    request: Request,
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

    user_dict = dict(row)
    request.state.user = user_dict
    return user_dict


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


def require_case_access(level: str = "view", allow_auditor: bool = True) -> Callable:
    """
    Implements §6.3 Role matrix for case access:
    - investigator/artist -> only cases with non-revoked case_access row
      (edit for mutations, view for reads)
    - supervisor -> all cases
    - auditor -> case metadata but no case content (sessions/images/statements)
    - admin -> no case content unless granted access
    """
    def dependency(
        request: Request,
        case_id: str = FastApiPath(...),
        user: dict = Depends(get_current_user),
        purpose: str = Depends(require_access_purpose),
        conn: Connection = Depends(get_connection),
    ) -> dict:
        role = user["role"]
        user_id = user["id"]

        # Check case exists
        case_row = conn.execute(
            text(
                """
                SELECT id, case_number, title, station, offence_summary, data_mode,
                       default_appearance_group, status, created_by, created_at, updated_at
                FROM cases
                WHERE id = :id
                """
            ),
            {"id": case_id},
        ).mappings().fetchone()
        if not case_row:
            raise AppError("NOT_FOUND", "Case not found")

        if role == "supervisor":
            return {"case": dict(case_row), "user": user, "purpose": purpose}

        if role == "auditor":
            if not allow_auditor:
                _log_access_denied(user, case_id, purpose, request, "Auditors cannot access sessions", conn)
                raise AppError("FORBIDDEN", "Auditors cannot access sessions")
            # Auditor can view case metadata only
            if level != "view":
                _log_access_denied(user, case_id, purpose, request, "Auditors cannot mutate cases", conn)
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
                _log_access_denied(user, case_id, purpose, request, "Access to this case has not been granted or was revoked", conn)
                raise AppError("FORBIDDEN", "Access to this case has not been granted or was revoked")

            granted_level = access_row["access_level"]
            if level == "edit" and granted_level != "edit":
                _log_access_denied(user, case_id, purpose, request, "Edit permission required for this operation", conn)
                raise AppError("FORBIDDEN", "Edit permission required for this operation")

            return {"case": dict(case_row), "user": user, "purpose": purpose}

        _log_access_denied(user, case_id, purpose, request, "Unauthorized role for case access", conn)
        raise AppError("FORBIDDEN", "Unauthorized role for case access")

    return dependency


def require_session_access(level: str = "view") -> Callable:
    """
    Implements session access control per §6.3 and §7.1:
    - auditor -> strictly forbidden (403 FORBIDDEN, writes access.denied with session's case_id)
    - supervisor -> allowed on all sessions
    - investigator/artist/admin -> allowed only if active non-revoked case_access exists for the session's case
      (edit required if level='edit')
    - require X-Access-Purpose
    """
    def dependency(
        request: Request,
        sid: str = FastApiPath(...),
        user: dict = Depends(get_current_user),
        purpose: str = Depends(require_access_purpose),
        conn: Connection = Depends(get_connection),
    ) -> dict:
        role = user["role"]
        user_id = user["id"]

        session_row = conn.execute(
            text(
                """
                SELECT id, case_id, witness_id, kind, status, current_round,
                       current_snapshot_id, locked_features_json, selected_image_id,
                       created_by, created_at, updated_at, completed_at
                FROM sessions
                WHERE id = :sid
                """
            ),
            {"sid": sid},
        ).mappings().fetchone()
        if not session_row:
            raise AppError("NOT_FOUND", f"Session '{sid}' not found")

        case_id = session_row["case_id"]

        # Auditor cannot access session content (§6.3, TB4.3)
        if role == "auditor":
            _log_access_denied(user, case_id, purpose, request, "Auditors cannot access sessions", conn)
            raise AppError("FORBIDDEN", "Auditors cannot access sessions")

        if role == "supervisor":
            return {"session": dict(session_row), "user": user, "purpose": purpose}

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
                _log_access_denied(user, case_id, purpose, request, "Access to this case has not been granted or was revoked", conn)
                raise AppError("FORBIDDEN", "Access to this case has not been granted or was revoked")

            if level == "edit" and access_row["access_level"] != "edit":
                _log_access_denied(user, case_id, purpose, request, "Edit permission required for this operation", conn)
                raise AppError("FORBIDDEN", "Edit permission required for this operation")

            return {"session": dict(session_row), "user": user, "purpose": purpose}

        _log_access_denied(user, case_id, purpose, request, "Unauthorized role for session access", conn)
        raise AppError("FORBIDDEN", "Unauthorized role for session access")

    return dependency
