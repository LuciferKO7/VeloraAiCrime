import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import require_case_access
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection

router = APIRouter(prefix="/cases", tags=["witnesses"])

ALLOWED_LANGUAGES = {"en", "ta", "hi", "te", "kn", "ml", "bn", "mr"}


class WitnessCreate(BaseModel):
    alias: str | None = None
    preferred_language: str


@router.get("/{case_id}/witnesses")
def list_witnesses(
    request: Request,
    case_access_info: dict = Depends(require_case_access("edit")),
    conn: Connection = Depends(get_connection),
):
    case_id = case_access_info["case"]["id"]
    rows = conn.execute(
        text(
            """
            SELECT id, case_id, alias, preferred_language, created_by, created_at
            FROM witnesses
            WHERE case_id = :cid
            ORDER BY created_at ASC
            """
        ),
        {"cid": case_id},
    ).mappings().fetchall()

    return [dict(r) for r in rows]


@router.post("/{case_id}/witnesses", status_code=201)
def create_witness(
    request: Request,
    body: WitnessCreate,
    case_access_info: dict = Depends(require_case_access("edit")),
    conn: Connection = Depends(get_connection),
):
    case_dict = case_access_info["case"]
    user = case_access_info["user"]
    purpose = case_access_info["purpose"]
    case_id = case_dict["id"]

    # 1. Validate preferred_language (§5 CHECK constraint & TB4.2)
    if body.preferred_language not in ALLOWED_LANGUAGES:
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid preferred_language '{body.preferred_language}'. Must be one of: {sorted(ALLOWED_LANGUAGES)}",
            details={"allowed": sorted(ALLOWED_LANGUAGES)},
            status_code=422,
        )

    # 2. Determine and validate alias (unique per case_id, alias)
    alias = body.alias.strip() if body.alias and body.alias.strip() else None
    if alias:
        existing = conn.execute(
            text("SELECT id FROM witnesses WHERE case_id = :cid AND alias = :alias"),
            {"cid": case_id, "alias": alias},
        ).fetchone()
        if existing:
            raise AppError(
                "VALIDATION_ERROR",
                f"Witness alias '{alias}' already exists in this case",
                details={"field": "alias"},
                status_code=422,
            )
    else:
        count = conn.execute(
            text("SELECT COUNT(*) FROM witnesses WHERE case_id = :cid"),
            {"cid": case_id},
        ).scalar() or 0
        alias = f"W-{count + 1:03d}"
        # Ensure collision-free
        while conn.execute(
            text("SELECT id FROM witnesses WHERE case_id = :cid AND alias = :alias"),
            {"cid": case_id, "alias": alias},
        ).fetchone():
            count += 1
            alias = f"W-{count + 1:03d}"

    witness_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO witnesses (id, case_id, alias, preferred_language, created_by, created_at)
                VALUES (:id, :cid, :alias, :lang, :uid, :now)
                """
            ),
            {
                "id": witness_id,
                "cid": case_id,
                "alias": alias,
                "lang": body.preferred_language,
                "uid": user["id"],
                "now": now_iso,
            },
        )
        write_audit_entry(
            conn,
            action="witness.create",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="witness",
            resource_id=witness_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={"alias": alias, "preferred_language": body.preferred_language},
        )

    return {
        "id": witness_id,
        "case_id": case_id,
        "alias": alias,
        "preferred_language": body.preferred_language,
        "created_by": user["id"],
        "created_at": now_iso,
    }

