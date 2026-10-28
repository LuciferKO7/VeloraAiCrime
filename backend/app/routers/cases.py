import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import get_current_user, require_case_access, require_role
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection

router = APIRouter(prefix="/cases", tags=["cases"])

VALID_APPEARANCE_GROUPS = (
    "south_asian",
    "east_asian",
    "southeast_asian",
    "white",
    "black",
    "middle_eastern",
    "latino",
    "mixed_other",
    "unspecified",
)


class CaseCreate(BaseModel):
    case_number: str
    title: str
    station: str | None = None
    offence_summary: str | None = None
    data_mode: str = "demo"
    default_appearance_group: str = "unspecified"


class CaseUpdate(BaseModel):
    title: str | None = None
    station: str | None = None
    offence_summary: str | None = None
    status: str | None = None
    default_appearance_group: str | None = None


@router.get("")
def list_cases(
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
):
    role = current_user["role"]
    if role == "auditor":
        # §6.3: Auditor receives metadata only; protected case content (e.g. offence_summary, station) is omitted
        rows = conn.execute(
            text(
                """
                SELECT id, case_number, title, status, data_mode,
                       default_appearance_group, created_at, updated_at
                FROM cases
                ORDER BY created_at DESC
                """
            )
        ).mappings().fetchall()
    elif role == "supervisor":
        rows = conn.execute(
            text(
                """
                SELECT id, case_number, title, station, status, data_mode,
                       default_appearance_group, created_at, updated_at
                FROM cases
                ORDER BY created_at DESC
                """
            )
        ).mappings().fetchall()
    elif role in ("investigator", "artist", "admin"):
        # investigator/artist/admin see cases with active (non-revoked) case_access grant
        rows = conn.execute(
            text(
                """
                SELECT c.id, c.case_number, c.title, c.station, c.status, c.data_mode,
                       c.default_appearance_group, c.created_at, c.updated_at
                FROM cases c
                JOIN case_access ca ON c.id = ca.case_id
                WHERE ca.user_id = :uid AND ca.revoked_at IS NULL
                ORDER BY c.created_at DESC
                """
            ),
            {"uid": current_user["id"]},
        ).mappings().fetchall()
    else:
        rows = []
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_case(
    request: Request,
    body: CaseCreate,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("investigator", "supervisor")),
):
    # 1. Uniqueness check for case_number (TB4.2)
    existing = conn.execute(
        text("SELECT id FROM cases WHERE case_number = :cn"),
        {"cn": body.case_number},
    ).fetchone()
    if existing:
        raise AppError(
            "VALIDATION_ERROR",
            f"Case number '{body.case_number}' already exists",
            details={"field": "case_number"},
            status_code=422,
        )

    # 2. Validation for data_mode and appearance group
    if body.data_mode not in ("demo", "real"):
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid data_mode '{body.data_mode}'. Allowed values: demo, real",
            status_code=422,
        )

    if body.default_appearance_group not in VALID_APPEARANCE_GROUPS:
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid default_appearance_group '{body.default_appearance_group}'",
            details={"allowed": list(VALID_APPEARANCE_GROUPS)},
            status_code=422,
        )

    case_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO cases (
                    id, case_number, title, station, offence_summary, data_mode,
                    default_appearance_group, status, created_by, created_at, updated_at
                ) VALUES (
                    :id, :case_number, :title, :station, :offence_summary, :data_mode,
                    :default_appearance_group, 'open', :created_by, :created_at, :created_at
                )
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
        write_audit_entry(
            conn,
            action="case.create",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="case",
            resource_id=case_id,
            case_id=case_id,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={"case_number": body.case_number, "title": body.title, "data_mode": body.data_mode},
        )

    return {
        "id": case_id,
        "case_number": body.case_number,
        "title": body.title,
        "status": "open",
        "data_mode": body.data_mode,
        "default_appearance_group": body.default_appearance_group,
        "created_at": now_iso,
    }


@router.get("/{case_id}")
def get_case(
    request: Request,
    case_access_info: dict = Depends(require_case_access("view")),
    conn: Connection = Depends(get_connection),
):
    case_dict = case_access_info["case"]
    user = case_access_info["user"]
    purpose = case_access_info["purpose"]
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    write_audit_entry(
        conn,
        action="case.view",
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        resource_type="case",
        resource_id=case_dict["id"],
        case_id=case_dict["id"],
        purpose=purpose,
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={"case_number": case_dict["case_number"]},
    )

    # Auditor receives metadata only; protected case content (e.g. offence_summary) is omitted (§6.3, TB4.3)
    if user["role"] == "auditor":
        return {
            "id": case_dict["id"],
            "case_number": case_dict["case_number"],
            "title": case_dict["title"],
            "status": case_dict["status"],
            "data_mode": case_dict["data_mode"],
            "default_appearance_group": case_dict["default_appearance_group"],
            "created_at": case_dict["created_at"],
            "updated_at": case_dict["updated_at"],
        }

    return case_dict


@router.patch("/{case_id}")
def update_case(
    request: Request,
    body: CaseUpdate,
    case_access_info: dict = Depends(require_case_access("edit")),
    conn: Connection = Depends(get_connection),
):
    case_dict = case_access_info["case"]
    user = case_access_info["user"]
    purpose = case_access_info["purpose"]
    case_id = case_dict["id"]

    update_fields = {}
    if body.title is not None:
        update_fields["title"] = body.title
    if body.station is not None:
        update_fields["station"] = body.station
    if body.offence_summary is not None:
        update_fields["offence_summary"] = body.offence_summary
    if body.status is not None:
        if body.status not in ("open", "closed", "archived"):
            raise AppError("VALIDATION_ERROR", f"Invalid status '{body.status}'", status_code=422)
        update_fields["status"] = body.status
    if body.default_appearance_group is not None:
        if body.default_appearance_group not in VALID_APPEARANCE_GROUPS:
            raise AppError(
                "VALIDATION_ERROR",
                f"Invalid default_appearance_group '{body.default_appearance_group}'",
                details={"allowed": list(VALID_APPEARANCE_GROUPS)},
                status_code=422,
            )
        update_fields["default_appearance_group"] = body.default_appearance_group

    now_iso = datetime.now(UTC).isoformat()
    update_fields["updated_at"] = now_iso

    set_clauses = [f"{k} = :{k}" for k in update_fields.keys()]
    sql = f"UPDATE cases SET {', '.join(set_clauses)} WHERE id = :case_id"
    params = dict(update_fields)
    params["case_id"] = case_id

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(text(sql), params)
        write_audit_entry(
            conn,
            action="case.update",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="case",
            resource_id=case_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=200,
            details={"updated_fields": list(update_fields.keys())},
        )

    updated_row = conn.execute(
        text("SELECT * FROM cases WHERE id = :id"),
        {"id": case_id},
    ).mappings().fetchone()
    return dict(updated_row)
