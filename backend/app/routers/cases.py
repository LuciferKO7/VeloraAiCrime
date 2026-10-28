import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.deps import get_current_user, require_case_access, require_role
from backend.app.db.session import get_connection

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseCreate(BaseModel):
    case_number: str
    title: str
    station: str | None = None
    offence_summary: str | None = None
    data_mode: str = "demo"
    default_appearance_group: str = "unspecified"


@router.get("")
def list_cases(
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
):
    role = current_user["role"]
    if role in ("supervisor", "auditor"):
        rows = conn.execute(text("SELECT id, case_number, title, station, status, data_mode, default_appearance_group, created_at FROM cases")).mappings().fetchall()
    elif role in ("investigator", "artist"):
        rows = conn.execute(
            text(
                """
                SELECT c.id, c.case_number, c.title, c.station, c.status, c.data_mode, c.default_appearance_group, c.created_at
                FROM cases c
                JOIN case_access ca ON c.id = ca.case_id
                WHERE ca.user_id = :uid AND ca.revoked_at IS NULL
                """
            ),
            {"uid": current_user["id"]},
        ).mappings().fetchall()
    else:
        rows = []
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_case(
    body: CaseCreate,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("investigator", "supervisor")),
):
    case_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            """
            INSERT INTO cases (id, case_number, title, station, offence_summary, data_mode, default_appearance_group, status, created_by, created_at, updated_at)
            VALUES (:id, :case_number, :title, :station, :offence_summary, :data_mode, :default_appearance_group, 'open', :created_by, :created_at, :created_at)
            """
        ),
        {
            "id": case_id,
            "case_number": body.case_number,
            "title": body.title,
            "station": body.station,
            "offence_summary": body.offence_summary,
            "data_mode": body.data_mode,
            "default_appearance_group": body.default_appearance_group,
            "created_by": current_user["id"],
            "created_at": now_iso,
        },
    )
    conn.commit()
    return {"id": case_id, "case_number": body.case_number, "title": body.title, "status": "open"}


@router.get("/{case_id}")
def get_case(
    case_access_info: dict = Depends(require_case_access("view")),
):
    # Returns case metadata
    return case_access_info["case"]
