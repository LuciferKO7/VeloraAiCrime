import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import get_current_user, require_role
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection
from backend.app.llm.guards import ATTRIBUTE_ENUMS

router = APIRouter(prefix="/glossary", tags=["glossary"])

VALID_GLOSSARY_STATUSES = {"pending", "approved", "rejected"}


class MapsToModel(BaseModel):
    attribute: str = Field(..., description="Target facial attribute key")
    value: str = Field(..., description="Target attribute enum value")


class SuggestTermRequest(BaseModel):
    language: str = Field(..., min_length=2, max_length=10, description="ISO language code, e.g. ta, hi, en")
    term: str = Field(..., min_length=1, max_length=100, description="Colloquial term or phrase")
    maps_to: MapsToModel = Field(..., description="Mapping to standard face attribute and enum value")
    suggested_by_llm_call_id: str | None = Field(None, description="Optional LLM call ID that suggested this")


class ReviewTermRequest(BaseModel):
    action: str = Field(..., description="Review action: 'approve' or 'reject'")


def _validate_maps_to(attribute: str, value: str) -> None:
    if attribute not in ATTRIBUTE_ENUMS:
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid attribute '{attribute}'. Must be one of valid facial attributes.",
            details={"allowed_attributes": sorted(ATTRIBUTE_ENUMS.keys())},
            status_code=422,
        )
    allowed_values = ATTRIBUTE_ENUMS[attribute]
    if value not in allowed_values:
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid enum value '{value}' for attribute '{attribute}'.",
            details={"allowed_values": sorted(allowed_values)},
            status_code=422,
        )


@router.get("")
def list_glossary(
    status: str | None = Query(None, description="Filter by status: pending, approved, rejected"),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("supervisor", "admin", "investigator", "artist")),
):
    """
    List glossary terms (§7, §12 Step B10).
    Allows filtering by status (pending, approved, rejected).
    """
    if status is not None:
        status_clean = status.strip().lower()
        if status_clean not in VALID_GLOSSARY_STATUSES:
            raise AppError(
                "VALIDATION_ERROR",
                f"Invalid status '{status}'. Must be one of {sorted(VALID_GLOSSARY_STATUSES)}",
                status_code=422,
            )
        rows = conn.execute(
            text(
                """
                SELECT id, language, term, maps_to_json, status, suggested_by_llm_call_id,
                       suggested_at, reviewed_by, reviewed_at
                FROM glossary_terms
                WHERE status = :status
                ORDER BY suggested_at DESC
                """
            ),
            {"status": status_clean},
        ).mappings().fetchall()
    else:
        rows = conn.execute(
            text(
                """
                SELECT id, language, term, maps_to_json, status, suggested_by_llm_call_id,
                       suggested_at, reviewed_by, reviewed_at
                FROM glossary_terms
                ORDER BY suggested_at DESC
                """
            )
        ).mappings().fetchall()

    results = []
    for r in rows:
        item = dict(r)
        try:
            item["maps_to"] = json.loads(item["maps_to_json"])
        except Exception:
            item["maps_to"] = {}
        results.append(item)
    return results


@router.post("/suggest", status_code=status.HTTP_201_CREATED)
def suggest_glossary_term(
    payload: SuggestTermRequest,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
):
    """
    Suggest a new colloquial/slang term mapping to standard FaceAttributes enum (§7, §12 Step B10).
    Validates maps_to attribute and value against ATTRIBUTE_ENUMS.
    """
    attribute = payload.maps_to.attribute.strip()
    val = payload.maps_to.value.strip()
    _validate_maps_to(attribute, val)

    lang = payload.language.strip().lower()
    term = payload.term.strip()

    # Check for existing term
    existing = conn.execute(
        text("SELECT id, status FROM glossary_terms WHERE language = :lang AND term = :term"),
        {"lang": lang, "term": term},
    ).fetchone()
    if existing:
        raise AppError(
            "CONFLICT_VERSION",
            f"Glossary term '{term}' for language '{lang}' already exists with status '{existing[1]}'",
            details={"existing_id": existing[0], "status": existing[1]},
            status_code=409,
        )

    term_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    maps_to_dict = {"attribute": attribute, "value": val}
    maps_to_json = json.dumps(maps_to_dict, separators=(",", ":"))

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO glossary_terms (
                    id, language, term, maps_to_json, status,
                    suggested_by_llm_call_id, suggested_at
                )
                VALUES (:id, :language, :term, :maps_to_json, 'pending', :call_id, :suggested_at)
                """
            ),
            {
                "id": term_id,
                "language": lang,
                "term": term,
                "maps_to_json": maps_to_json,
                "call_id": payload.suggested_by_llm_call_id,
                "suggested_at": now_iso,
            },
        )

    return {
        "id": term_id,
        "language": lang,
        "term": term,
        "maps_to": maps_to_dict,
        "maps_to_json": maps_to_json,
        "status": "pending",
        "suggested_by_llm_call_id": payload.suggested_by_llm_call_id,
        "suggested_at": now_iso,
        "reviewed_by": None,
        "reviewed_at": None,
    }


@router.post("/{term_id}/review")
def review_glossary_term(
    term_id: str,
    payload: ReviewTermRequest,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("supervisor", "admin")),
):
    """
    Supervisor or admin reviews a suggested glossary term (approve or reject) (§6.3, §12 Step B10).
    Atomically updates status and records audit log.
    """
    action = payload.action.strip().lower()
    if action not in ("approve", "reject"):
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid review action '{payload.action}'. Must be 'approve' or 'reject'.",
            status_code=422,
        )

    row = conn.execute(
        text("SELECT id, language, term, maps_to_json, status FROM glossary_terms WHERE id = :id"),
        {"id": term_id},
    ).mappings().fetchone()
    if not row:
        raise AppError("NOT_FOUND", f"Glossary term '{term_id}' not found", status_code=404)

    if row["status"] != "pending":
        raise AppError(
            "VALIDATION_ERROR",
            f"Glossary term is already in '{row['status']}' state and cannot be reviewed again.",
            details={"current_status": row["status"]},
            status_code=422,
        )

    new_status = "approved" if action == "approve" else "rejected"
    now_iso = datetime.now(UTC).isoformat()

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                UPDATE glossary_terms
                SET status = :status, reviewed_by = :uid, reviewed_at = :now
                WHERE id = :id
                """
            ),
            {"status": new_status, "uid": current_user["id"], "now": now_iso, "id": term_id},
        )
        write_audit_entry(
            conn,
            action="glossary.review",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="glossary_term",
            resource_id=term_id,
            details={
                "language": row["language"],
                "term": row["term"],
                "action": action,
                "old_status": "pending",
                "new_status": new_status,
                "reviewed_by": current_user["username"],
            },
        )

    try:
        maps_to = json.loads(row["maps_to_json"])
    except Exception:
        maps_to = {}

    return {
        "id": term_id,
        "language": row["language"],
        "term": row["term"],
        "maps_to": maps_to,
        "maps_to_json": row["maps_to_json"],
        "status": new_status,
        "reviewed_by": current_user["id"],
        "reviewed_at": now_iso,
    }
