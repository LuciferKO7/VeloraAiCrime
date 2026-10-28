import uuid
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import get_iso_timestamp, write_audit_entry
from backend.app.auth.deps import get_current_user, require_role
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection
from backend.app.services.gallery_service import gallery_index, save_gallery_image
from backend.app.services.ml_proxy import ml_proxy

router = APIRouter(prefix="/gallery", tags=["gallery"])

ALLOWED_SOURCES = ("synthetic", "consented_volunteer")
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB limit


@router.get("")
def list_gallery_faces(
    conn: Connection = Depends(get_connection),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    Lists all faces stored in the gallery (§7.1, Step B11).
    """
    rows = conn.execute(
        text(
            """
            SELECT id, label, source, consent_ref, image_path, embedding_model_version, added_by, added_at
            FROM gallery_faces
            ORDER BY added_at DESC, id ASC
            """
        )
    ).mappings().fetchall()

    return [dict(r) for r in rows]


@router.post("/faces", status_code=status.HTTP_201_CREATED)
def upload_gallery_face(
    file: UploadFile = File(...),
    label: str = Form(...),
    source: str = Form(...),
    consent_ref: str | None = Form(None),
    conn: Connection = Depends(get_connection),
    current_user: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    """
    Uploads a synthetic or consented-volunteer face into the gallery (§7.1, Step B11).
    Enforces that only admin may upload, validates source and consent_ref,
    embeds via ML service proxy, and atomically persists the record and audit entry.
    """
    clean_label = label.strip() if label else ""
    if not clean_label:
        raise AppError("VALIDATION_ERROR", "Field 'label' is required and cannot be blank", status_code=422)

    clean_source = source.strip() if source else ""
    if clean_source not in ALLOWED_SOURCES:
        raise AppError(
            "VALIDATION_ERROR",
            f"Field 'source' must be one of {ALLOWED_SOURCES}, got '{clean_source}'",
            status_code=422,
        )

    clean_consent = consent_ref.strip() if consent_ref else None
    if clean_source == "consented_volunteer":
        if not clean_consent:
            raise AppError(
                "VALIDATION_ERROR",
                "Field 'consent_ref' is required and cannot be blank when source is 'consented_volunteer'",
                status_code=422,
            )

    try:
        image_bytes = file.file.read()
    except Exception as exc:
        raise AppError("VALIDATION_ERROR", f"Could not read uploaded file: {exc}", status_code=422) from exc

    if not image_bytes:
        raise AppError("VALIDATION_ERROR", "Uploaded file is empty", status_code=422)

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise AppError("VALIDATION_ERROR", "Uploaded image exceeds 10 MB limit", status_code=422)

    # Call ML service proxy to embed image
    emb_floats, model_version = ml_proxy.get_embedding(image_bytes)

    # Convert to 512 float32 bytes for SQLite BLOB
    emb_np = np.array(emb_floats, dtype=np.float32)
    emb_bytes = emb_np.tobytes()

    face_id = str(uuid.uuid4())
    image_rel_path = save_gallery_image(face_id, image_bytes)
    now = get_iso_timestamp()

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO gallery_faces (
                    id, label, source, consent_ref, image_path,
                    embedding, embedding_model_version, added_by, added_at
                )
                VALUES (
                    :id, :label, :source, :consent_ref, :image_path,
                    :embedding, :embedding_model_version, :added_by, :added_at
                )
                """
            ),
            {
                "id": face_id,
                "label": clean_label,
                "source": clean_source,
                "consent_ref": clean_consent,
                "image_path": image_rel_path,
                "embedding": emb_bytes,
                "embedding_model_version": model_version,
                "added_by": current_user["id"],
                "added_at": now,
            },
        )

        write_audit_entry(
            conn,
            action="gallery.add",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="gallery_face",
            resource_id=face_id,
            case_id=None,
            purpose=None,
            ip=None,
            status_code=201,
            details={
                "label": clean_label,
                "source": clean_source,
                "consent_ref": clean_consent,
                "model_version": model_version,
            },
        )

    # Refresh in-memory matrix
    gallery_index.add_face(face_id, emb_np)

    return {
        "id": face_id,
        "label": clean_label,
        "source": clean_source,
        "consent_ref": clean_consent,
        "image_path": image_rel_path,
        "embedding_model_version": model_version,
        "added_by": current_user["id"],
        "added_at": now,
    }
