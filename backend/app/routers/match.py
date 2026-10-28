import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import get_iso_timestamp, write_audit_entry
from backend.app.auth.deps import get_current_user, require_access_purpose
from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection
from backend.app.services.gallery_service import gallery_index
from backend.app.services.ml_proxy import ml_proxy

router = APIRouter(prefix="/match", tags=["match"])

DISCLAIMER_TEXT = "AI-generated investigative aid — not a photograph, not evidence of identity."


class MatchSearchRequest(BaseModel):
    session_id: str
    image_id: str
    top_k: int = Field(5, ge=1, le=50)


@router.post("/search", status_code=status.HTTP_200_OK)
@router.post("", status_code=status.HTTP_200_OK)
def search_face_matches(
    payload: MatchSearchRequest,
    conn: Connection = Depends(get_connection),
    current_user: dict[str, Any] = Depends(get_current_user),
    x_access_purpose: str = Depends(require_access_purpose),
) -> dict[str, Any]:
    """
    Compares suspect composite image embedding against gallery matrix (§7.1, §8.7, Step B11).
    Returns top-k possible leads with similarity scores and mandatory disclaimer.
    """
    if current_user["role"] == "auditor":
        raise AppError("FORBIDDEN", "Auditors cannot perform match searches", status_code=403)

    # 1. Fetch and validate session
    session_row = conn.execute(
        text("SELECT id, case_id FROM sessions WHERE id = :id"),
        {"id": payload.session_id},
    ).mappings().fetchone()
    if not session_row:
        raise AppError("NOT_FOUND", "Session not found", status_code=404)

    case_id = session_row["case_id"]

    # 2. Check case access for user
    if current_user["role"] in ("investigator", "artist", "admin"):
        access_row = conn.execute(
            text(
                """
                SELECT access_level FROM case_access
                WHERE case_id = :cid AND user_id = :uid AND revoked_at IS NULL
                """
            ),
            {"cid": case_id, "uid": current_user["id"]},
        ).mappings().fetchone()
        if not access_row:
            with atomic_mutation(conn):
                write_audit_entry(
                    conn,
                    action="access.denied",
                    user_id=current_user["id"],
                    username=current_user["username"],
                    role=current_user["role"],
                    resource_type="case",
                    resource_id=case_id,
                    case_id=case_id,
                    purpose=x_access_purpose,
                    status_code=403,
                    details={"session_id": payload.session_id, "required_level": "view"},
                )
            raise AppError("FORBIDDEN", "User does not have access to this case", status_code=403)

    # 3. Fetch image record
    img_row = conn.execute(
        text("SELECT id, session_id, storage_path FROM images WHERE id = :id"),
        {"id": payload.image_id},
    ).mappings().fetchone()
    if not img_row:
        raise AppError("NOT_FOUND", "Image not found", status_code=404)

    if img_row["session_id"] != payload.session_id:
        raise AppError("VALIDATION_ERROR", "Image does not belong to specified session", status_code=400)

    # 4. Read image file from disk
    img_path = Path(settings.STORAGE_DIR) / img_row["storage_path"]
    if not img_path.exists() or not img_path.is_file():
        raise AppError("NOT_FOUND", "Image file not found on disk", status_code=404)

    raw_bytes = img_path.read_bytes()

    # 5. Obtain query embedding via ML service
    q_emb, _ = ml_proxy.get_embedding(raw_bytes)

    # 6. Compute cosine similarity against in-memory gallery matrix
    matches = gallery_index.search(q_emb, top_k=payload.top_k, engine_or_conn=conn)

    # 7. Hydrate matches with gallery face labels and image paths
    face_details: dict[str, dict[str, Any]] = {}
    if matches:
        face_ids = [m["gallery_face_id"] for m in matches]
        # Using bind parameters safely
        placeholders = ", ".join(f":f_{i}" for i in range(len(face_ids)))
        params = {f"f_{i}": fid for i, fid in enumerate(face_ids)}
        face_rows = conn.execute(
            text(
                f"""
                SELECT id, label, source, consent_ref, image_path
                FROM gallery_faces
                WHERE id IN ({placeholders})
                """
            ),
            params,
        ).mappings().fetchall()
        for r in face_rows:
            face_details[r["id"]] = dict(r)

    search_id = str(uuid.uuid4())
    now = get_iso_timestamp()

    # 8. Persist search and results atomically
    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO match_searches (id, session_id, image_id, top_k, created_by, created_at)
                VALUES (:id, :session_id, :image_id, :top_k, :created_by, :created_at)
                """
            ),
            {
                "id": search_id,
                "session_id": payload.session_id,
                "image_id": payload.image_id,
                "top_k": payload.top_k,
                "created_by": current_user["id"],
                "created_at": now,
            },
        )

        for match in matches:
            res_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    INSERT INTO match_results (id, search_id, gallery_face_id, rank, similarity)
                    VALUES (:id, :search_id, :gallery_face_id, :rank, :similarity)
                    """
                ),
                {
                    "id": res_id,
                    "search_id": search_id,
                    "gallery_face_id": match["gallery_face_id"],
                    "rank": match["rank"],
                    "similarity": match["similarity"],
                },
            )

        write_audit_entry(
            conn,
            action="match.search",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="match_search",
            resource_id=search_id,
            case_id=case_id,
            purpose=x_access_purpose,
            status_code=200,
            details={
                "session_id": payload.session_id,
                "image_id": payload.image_id,
                "top_k": payload.top_k,
                "result_count": len(matches),
            },
        )

    hydrated_results = []
    for m in matches:
        f_info = face_details.get(m["gallery_face_id"], {})
        hydrated_results.append(
            {
                "rank": m["rank"],
                "gallery_face_id": m["gallery_face_id"],
                "similarity": m["similarity"],
                "label": f_info.get("label", ""),
                "source": f_info.get("source", ""),
                "image_path": f_info.get("image_path", ""),
            }
        )

    return {
        "search_id": search_id,
        "session_id": payload.session_id,
        "image_id": payload.image_id,
        "top_k": payload.top_k,
        "results": hydrated_results,
        "message": f"Found {len(matches)} possible leads",
        "disclaimer": DISCLAIMER_TEXT,
    }
