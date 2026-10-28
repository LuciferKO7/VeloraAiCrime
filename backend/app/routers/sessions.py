import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import require_case_access, require_session_access
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection
from backend.app.services.sessions import assemble_session_state

router = APIRouter(tags=["sessions"])


class SessionCreate(BaseModel):
    witness_id: str
    kind: str = "face"  # 'face' | 'scene'


class SessionComplete(BaseModel):
    final_image_id: str | None = None


@router.get("/cases/{case_id}/sessions")
def list_case_sessions(
    request: Request,
    case_access_info: dict = Depends(require_case_access("view", allow_auditor=False)),
    conn: Connection = Depends(get_connection),
):
    case_id = case_access_info["case"]["id"]
    rows = conn.execute(
        text(
            """
            SELECT id, case_id, witness_id, kind, status, current_round,
                   current_snapshot_id, selected_image_id, created_by, created_at, updated_at
            FROM sessions
            WHERE case_id = :cid
            ORDER BY created_at DESC
            """
        ),
        {"cid": case_id},
    ).mappings().fetchall()

    return [dict(r) for r in rows]


@router.post("/cases/{case_id}/sessions", status_code=201)
def create_session(
    request: Request,
    body: SessionCreate,
    case_access_info: dict = Depends(require_case_access("edit")),
    conn: Connection = Depends(get_connection),
):
    case_dict = case_access_info["case"]
    user = case_access_info["user"]
    purpose = case_access_info["purpose"]
    case_id = case_dict["id"]

    # 1. Validate kind (§5 CHECK constraint)
    if body.kind not in ("face", "scene"):
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid session kind '{body.kind}'. Allowed values: face, scene",
            status_code=422,
        )

    # 2. Validate witness exists and belongs to this case
    witness_row = conn.execute(
        text("SELECT id FROM witnesses WHERE id = :wid AND case_id = :cid"),
        {"wid": body.witness_id, "cid": case_id},
    ).fetchone()
    if not witness_row:
        raise AppError(
            "NOT_FOUND",
            f"Witness '{body.witness_id}' not found for case '{case_id}'",
            status_code=404,
        )

    session_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO sessions (
                    id, case_id, witness_id, kind, status, current_round,
                    current_snapshot_id, locked_features_json, selected_image_id,
                    created_by, created_at, updated_at
                ) VALUES (
                    :id, :cid, :wid, :kind, 'active', 0,
                    NULL, '[]', NULL,
                    :uid, :now, :now
                )
                """
            ),
            {
                "id": session_id,
                "cid": case_id,
                "wid": body.witness_id,
                "kind": body.kind,
                "uid": user["id"],
                "now": now_iso,
            },
        )
        write_audit_entry(
            conn,
            action="session.create",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="session",
            resource_id=session_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={"witness_id": body.witness_id, "kind": body.kind},
        )

    return {
        "id": session_id,
        "case_id": case_id,
        "witness_id": body.witness_id,
        "kind": body.kind,
        "status": "active",
        "current_round": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }


@router.get("/sessions/{sid}")
def get_session(
    request: Request,
    session_access_info: dict = Depends(require_session_access("view")),
    conn: Connection = Depends(get_connection),
):
    session_dict = session_access_info["session"]
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    sid = session_dict["id"]
    case_id = session_dict["case_id"]

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    write_audit_entry(
        conn,
        action="session.view",
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        resource_type="session",
        resource_id=sid,
        case_id=case_id,
        purpose=purpose,
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={"case_id": case_id},
    )

    return assemble_session_state(conn, session_dict)


@router.post("/sessions/{sid}/complete")
def complete_session(
    request: Request,
    body: SessionComplete,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = session_access_info["session"]
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    sid = session_dict["id"]
    case_id = session_dict["case_id"]

    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        if body.final_image_id:
            conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET status = 'completed', completed_at = :now, updated_at = :now, selected_image_id = :img_id
                    WHERE id = :sid
                    """
                ),
                {"sid": sid, "now": now_iso, "img_id": body.final_image_id},
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET status = 'completed', completed_at = :now, updated_at = :now
                    WHERE id = :sid
                    """
                ),
                {"sid": sid, "now": now_iso},
            )
        write_audit_entry(
            conn,
            action="session.complete",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="session",
            resource_id=sid,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=200,
            details={"final_image_id": body.final_image_id},
        )

    return {"id": sid, "status": "completed", "completed_at": now_iso}

