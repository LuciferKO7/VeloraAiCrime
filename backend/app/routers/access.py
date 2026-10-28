import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import require_access_purpose, require_role
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection

router = APIRouter(prefix="/cases", tags=["access"])


class AccessGrantRequest(BaseModel):
    user_id: str
    access_level: str  # 'view' | 'edit'


@router.get("/{case_id}/access")
def list_case_access(
    request: Request,
    case_id: str,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("supervisor")),
    purpose: str = Depends(require_access_purpose),
):
    # Verify case exists
    case_row = conn.execute(
        text("SELECT id FROM cases WHERE id = :cid"),
        {"cid": case_id},
    ).fetchone()
    if not case_row:
        raise AppError("NOT_FOUND", f"Case '{case_id}' not found", status_code=404)

    rows = conn.execute(
        text(
            """
            SELECT ca.id, ca.case_id, ca.user_id, u.username, u.full_name, u.role,
                   ca.access_level, ca.granted_by, ca.granted_at, ca.revoked_at
            FROM case_access ca
            JOIN users u ON ca.user_id = u.id
            WHERE ca.case_id = :cid
            ORDER BY ca.granted_at DESC
            """
        ),
        {"cid": case_id},
    ).mappings().fetchall()

    return [dict(r) for r in rows]


@router.post("/{case_id}/access", status_code=201)
def grant_case_access(
    request: Request,
    case_id: str,
    body: AccessGrantRequest,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("supervisor")),
    purpose: str = Depends(require_access_purpose),
):
    if body.access_level not in ("view", "edit"):
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid access_level '{body.access_level}'. Allowed values: view, edit",
            status_code=422,
        )

    # Verify case exists
    case_row = conn.execute(
        text("SELECT id FROM cases WHERE id = :cid"),
        {"cid": case_id},
    ).fetchone()
    if not case_row:
        raise AppError("NOT_FOUND", f"Case '{case_id}' not found", status_code=404)

    # Verify target user exists
    target_user = conn.execute(
        text("SELECT id, username, role FROM users WHERE id = :uid"),
        {"uid": body.user_id},
    ).mappings().fetchone()
    if not target_user:
        raise AppError("NOT_FOUND", f"User '{body.user_id}' not found", status_code=404)

    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    existing = conn.execute(
        text("SELECT id FROM case_access WHERE case_id = :cid AND user_id = :uid"),
        {"cid": case_id, "uid": body.user_id},
    ).fetchone()

    with atomic_mutation(conn):
        if existing:
            access_id = str(existing[0])
            conn.execute(
                text(
                    """
                    UPDATE case_access
                    SET access_level = :lvl, granted_by = :gb, granted_at = :ga, revoked_at = NULL
                    WHERE id = :id
                    """
                ),
                {
                    "id": access_id,
                    "lvl": body.access_level,
                    "gb": current_user["id"],
                    "ga": now_iso,
                },
            )
        else:
            access_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    INSERT INTO case_access (id, case_id, user_id, access_level, granted_by, granted_at, revoked_at)
                    VALUES (:id, :cid, :uid, :lvl, :gb, :ga, NULL)
                    """
                ),
                {
                    "id": access_id,
                    "cid": case_id,
                    "uid": body.user_id,
                    "lvl": body.access_level,
                    "gb": current_user["id"],
                    "ga": now_iso,
                },
            )
        write_audit_entry(
            conn,
            action="case.access_grant",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="case_access",
            resource_id=access_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={
                "granted_user_id": body.user_id,
                "granted_username": target_user["username"],
                "access_level": body.access_level,
            },
        )

    return {
        "id": access_id,
        "case_id": case_id,
        "user_id": body.user_id,
        "access_level": body.access_level,
        "granted_at": now_iso,
    }


@router.delete("/{case_id}/access/{user_id}")
def revoke_case_access(
    request: Request,
    case_id: str,
    user_id: str,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("supervisor")),
    purpose: str = Depends(require_access_purpose),
):
    row = conn.execute(
        text("SELECT id FROM case_access WHERE case_id = :cid AND user_id = :uid"),
        {"cid": case_id, "uid": user_id},
    ).fetchone()
    if not row:
        raise AppError("NOT_FOUND", "Access grant not found", status_code=404)

    access_id = str(row[0])
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text("UPDATE case_access SET revoked_at = :now WHERE id = :id"),
            {"id": access_id, "now": now_iso},
        )
        write_audit_entry(
            conn,
            action="case.access_revoke",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="case_access",
            resource_id=access_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=200,
            details={"revoked_user_id": user_id},
        )

    return {
        "status": "revoked",
        "case_id": case_id,
        "user_id": user_id,
        "revoked_at": now_iso,
    }

