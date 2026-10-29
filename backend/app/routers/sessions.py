import base64
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import require_case_access, require_session_access
from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_connection
from backend.app.services.ml_proxy import MINIMAL_PNG_BYTES, ml_proxy
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


class StatementCreate(BaseModel):
    text: str | None = None
    speaker: str = "witness"
    input_mode: str = "text"
    audio_sha256: str | None = None
    audio_base64: str | None = None
    language: str | None = None


class AttributesUpdate(BaseModel):
    attributes: dict[str, Any]
    unmapped_notes: list[str] | None = None


@router.post("/sessions/{sid}/transcribe")
async def transcribe_session_audio(
    sid: str,
    request: Request,
    language_hint: str | None = Query(None),
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = session_access_info["session"]
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            raw_b64 = body.get("audio_base64") or body.get("audio") or ""
            audio_bytes = base64.b64decode(raw_b64)
            if not language_hint:
                language_hint = body.get("language_hint") or body.get("language")
        except Exception as exc:
            raise AppError("VALIDATION_ERROR", "Invalid JSON or audio_base64 payload", status_code=400) from exc
    else:
        audio_bytes = await request.body()

    if not audio_bytes:
        raise AppError("VALIDATION_ERROR", "Audio payload is empty", status_code=400)

    from backend.app.services.speech_proxy import SpeechProxyClient, save_audio_bytes
    rel_path, audio_sha = save_audio_bytes(audio_bytes, suffix=".wav")

    proxy = SpeechProxyClient()
    transcription = proxy.transcribe(
        audio_bytes=audio_bytes,
        filename="audio.wav",
        language_hint=language_hint,
    )

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    with atomic_mutation(conn):
        write_audit_entry(
            conn,
            action="speech.transcribe",
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
            details={
                "audio_sha256": audio_sha,
                "detected_language": transcription["language"],
                "audio_path": rel_path,
                "duration_s": transcription.get("duration_s"),
            },
        )

    return {
        "text": transcription["text"],
        "language": transcription["language"],
        "audio_sha256": audio_sha,
        "duration_s": transcription.get("duration_s"),
    }


@router.post("/sessions/{sid}/statements", status_code=201)
def submit_statement(
    request: Request,
    body: StatementCreate,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    from backend.app.services.speech_proxy import SpeechProxyClient, save_audio_bytes
    from backend.app.services.statement_pipeline import (
        detect_language,
        generate_next_question,
        merge_attributes,
        parse_statement,
        suggest_glossary_terms_background,
        translate_text,
    )

    if body.speaker not in ("witness", "officer", "assistant", "system"):
        raise AppError("VALIDATION_ERROR", f"Invalid speaker '{body.speaker}'", status_code=422)
    if body.input_mode not in ("text", "voice"):
        raise AppError("VALIDATION_ERROR", f"Invalid input_mode '{body.input_mode}'", status_code=422)

    session_dict = session_access_info["session"]
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    sid = session_dict["id"]
    case_id = session_dict["case_id"]
    wid = session_dict["witness_id"]

    # Handle voice mode with audio_base64
    if body.input_mode == "voice" and not body.text:
        if not body.audio_base64:
            raise AppError("VALIDATION_ERROR", "Voice statement requires audio_base64 or text", status_code=422)
        try:
            raw_audio = base64.b64decode(body.audio_base64)
        except Exception as exc:
            raise AppError("VALIDATION_ERROR", "Invalid audio_base64 encoding", status_code=422) from exc
        rel_path, audio_sha = save_audio_bytes(raw_audio, suffix=".wav")
        proxy = SpeechProxyClient()
        trans = proxy.transcribe(raw_audio, language_hint=body.language)
        body.text = trans["text"]
        body.audio_sha256 = audio_sha
        if not body.language:
            body.language = trans["language"]

        # Audit voice transcription
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        with atomic_mutation(conn):
            write_audit_entry(
                conn,
                action="speech.transcribe",
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
                details={
                    "audio_sha256": audio_sha,
                    "detected_language": trans["language"],
                    "audio_path": rel_path,
                },
            )

    if not body.text:
        raise AppError("VALIDATION_ERROR", "Statement text is required", status_code=422)

    case_row = conn.execute(
        text("SELECT * FROM cases WHERE id = :cid"),
        {"cid": case_id},
    ).mappings().fetchone()
    case_dict = dict(case_row) if case_row else {}

    # 1. Fetch witness preferred_language hint
    w_row = conn.execute(
        text("SELECT preferred_language FROM witnesses WHERE id = :wid"),
        {"wid": wid},
    ).fetchone()
    witness_hint = w_row[0] if w_row else "en"

    # 2. Language Detection
    lang = body.language or detect_language(body.text, preferred_hint=witness_hint)
    if lang not in ("en", "ta", "hi", "te", "kn", "ml", "bn", "mr"):
        lang = "en"

    # 3. Translation
    english_text, trans_engine = translate_text(
        body.text,
        lang,
        case_id=case_id,
        session_id=sid,
    )

    # 4. Fetch current attributes and latest version
    snap_id = session_dict.get("current_snapshot_id")
    current_attrs: dict[str, Any] = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}
    if snap_id:
        snap_row = conn.execute(
            text("SELECT attributes_json FROM attribute_snapshots WHERE id = :snap_id"),
            {"snap_id": snap_id},
        ).fetchone()
        if snap_row and snap_row[0]:
            try:
                current_attrs = json.loads(snap_row[0])
            except Exception:
                current_attrs = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}

    latest_ver_row = conn.execute(
        text("SELECT MAX(version) FROM attribute_snapshots WHERE session_id = :sid"),
        {"sid": sid},
    ).scalar()
    new_version = (latest_ver_row or 0) + 1

    # 5. Parse and apply guards
    guarded_delta, llm_call_id = parse_statement(
        english_text,
        current_attrs,
        conn=conn,
        case_id=case_id,
        session_id=sid,
        original_lang=lang,
    )

    # 6. Merge attributes
    merged_attrs = merge_attributes(current_attrs, guarded_delta)

    # 7. Next Question & Assumptions derivation
    next_q = generate_next_question(merged_attrs, case_id=case_id, session_id=sid)

    from backend.app.services.sessions import SALIENT_KEYS

    assumptions = []
    attr_map = merged_attrs.get("attributes") or {}
    for key in SALIENT_KEYS:
        item = attr_map.get(key)
        if not item or item.get("value") is None:
            assumptions.append({"key": key, "value": None, "reason": "not_stated_varied_across_variants"})
        elif item.get("source") == "inferred":
            assumptions.append({"key": key, "value": item.get("value"), "reason": "inferred_from_wording"})

    # 8. Atomic persistence
    stmt_id = str(uuid.uuid4())
    new_snap_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO statements (
                    id, session_id, speaker, original_text, original_lang, english_text,
                    translation_engine, input_mode, audio_sha256, created_by, created_at
                ) VALUES (
                    :id, :session_id, :speaker, :original_text, :original_lang, :english_text,
                    :translation_engine, :input_mode, :audio_sha256, :created_by, :created_at
                )
                """
            ),
            {
                "id": stmt_id,
                "session_id": sid,
                "speaker": body.speaker,
                "original_text": body.text,
                "original_lang": lang,
                "english_text": english_text,
                "translation_engine": trans_engine,
                "input_mode": body.input_mode,
                "audio_sha256": body.audio_sha256,
                "created_by": user["id"],
                "created_at": now_iso,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO attribute_snapshots (
                    id, session_id, version, attributes_json, derived_from_statement_id,
                    llm_call_id, change_source, created_at
                ) VALUES (
                    :id, :session_id, :version, :attributes_json, :derived_from_statement_id,
                    :llm_call_id, 'statement', :created_at
                )
                """
            ),
            {
                "id": new_snap_id,
                "session_id": sid,
                "version": new_version,
                "attributes_json": json.dumps(merged_attrs),
                "derived_from_statement_id": stmt_id,
                "llm_call_id": llm_call_id,
                "created_at": now_iso,
            },
        )
        conn.execute(
            text("UPDATE sessions SET current_snapshot_id = :snap_id, updated_at = :now WHERE id = :sid"),
            {"snap_id": new_snap_id, "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="statement.create",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="statement",
            resource_id=stmt_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={
                "session_id": sid,
                "original_lang": lang,
                "translation_engine": trans_engine,
                "snapshot_version": new_version,
            },
        )

    # 9. Background glossary suggest for demo cases
    if case_dict.get("data_mode") == "demo":
        unmapped = merged_attrs.get("unmapped_notes") or []
        suggest_glossary_terms_background(unmapped, case_id, sid, lang)

    return {
        "statement": {
            "id": stmt_id,
            "session_id": sid,
            "speaker": body.speaker,
            "original_text": body.text,
            "original_lang": lang,
            "english_text": english_text,
            "translation_engine": trans_engine,
            "input_mode": body.input_mode,
            "audio_sha256": body.audio_sha256,
            "created_at": now_iso,
        },
        "parsed_attributes": guarded_delta,
        "attributes": merged_attrs,
        "assumptions": assumptions,
        "next_question": next_q,
    }


@router.put("/sessions/{sid}/attributes")
def update_session_attributes(
    request: Request,
    body: AttributesUpdate,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    from backend.app.services.statement_pipeline import merge_attributes

    session_dict = session_access_info["session"]
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    sid = session_dict["id"]
    case_id = session_dict["case_id"]

    # 1. Fetch current attributes
    snap_id = session_dict.get("current_snapshot_id")
    current_attrs: dict[str, Any] = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}
    if snap_id:
        snap_row = conn.execute(
            text("SELECT attributes_json FROM attribute_snapshots WHERE id = :snap_id"),
            {"snap_id": snap_id},
        ).fetchone()
        if snap_row and snap_row[0]:
            try:
                current_attrs = json.loads(snap_row[0])
            except Exception:
                current_attrs = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}

    latest_ver_row = conn.execute(
        text("SELECT MAX(version) FROM attribute_snapshots WHERE session_id = :sid"),
        {"sid": sid},
    ).scalar()
    new_version = (latest_ver_row or 0) + 1

    # 2. Format user edit delta with source='user_edit'
    user_delta_attrs = {}
    for k, v in body.attributes.items():
        if isinstance(v, dict):
            item = dict(v)
            item["source"] = "user_edit"
            user_delta_attrs[k] = item
        else:
            user_delta_attrs[k] = {"value": v, "source": "user_edit", "confidence": "sure"}

    user_delta: dict[str, Any] = {"attributes": user_delta_attrs}
    if body.unmapped_notes is not None:
        user_delta["unmapped_notes"] = body.unmapped_notes

    merged_attrs = merge_attributes(current_attrs, user_delta, source_override="user_edit")

    from backend.app.services.sessions import SALIENT_KEYS

    assumptions = []
    attr_map = merged_attrs.get("attributes") or {}
    for key in SALIENT_KEYS:
        item = attr_map.get(key)
        if not item or item.get("value") is None:
            assumptions.append({"key": key, "value": None, "reason": "not_stated_varied_across_variants"})
        elif item.get("source") == "inferred":
            assumptions.append({"key": key, "value": item.get("value"), "reason": "inferred_from_wording"})

    new_snap_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO attribute_snapshots (
                    id, session_id, version, attributes_json, derived_from_statement_id,
                    llm_call_id, change_source, created_at
                ) VALUES (
                    :id, :session_id, :version, :attributes_json, NULL,
                    NULL, 'user_edit', :created_at
                )
                """
            ),
            {
                "id": new_snap_id,
                "session_id": sid,
                "version": new_version,
                "attributes_json": json.dumps(merged_attrs),
                "created_at": now_iso,
            },
        )
        conn.execute(
            text("UPDATE sessions SET current_snapshot_id = :snap_id, updated_at = :now WHERE id = :sid"),
            {"snap_id": new_snap_id, "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="attributes.update",
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
            details={
                "snapshot_version": new_version,
                "updated_keys": list(body.attributes.keys()),
            },
        )

    return {
        "snapshot_id": new_snap_id,
        "version": new_version,
        "attributes": merged_attrs,
        "assumptions": assumptions,
    }


class RoundGenerateRequest(BaseModel):
    num_variants: int = Field(default=6, ge=1, le=12)
    seed: int | None = None
    axes: dict[str, Any] = Field(default_factory=dict)


class RoundEvolveRequest(BaseModel):
    parent_round_id: str | None = None
    feedback: dict[str, Any] = Field(default_factory=dict)
    num_variants: int = Field(default=6, ge=1, le=12)


class RoundEditRequest(BaseModel):
    parent_image_id: str
    instruction_text: str
    kind: str = Field(default="edit", pattern="^(edit|transform)$")
    region: str | None = None
    mask_b64: str | None = None


def format_round_dict(round_row: dict[str, Any], images_rows: list[dict[str, Any]]) -> dict[str, Any]:
    images = []
    for img in images_rows:
        img_id = img["id"]
        variant_axes = {}
        if img.get("variant_axes_json"):
            try:
                variant_axes = json.loads(img["variant_axes_json"]) if isinstance(img["variant_axes_json"], str) else img["variant_axes_json"]
            except Exception:
                variant_axes = {}
        model_versions = {}
        if img.get("model_versions_json"):
            try:
                model_versions = json.loads(img["model_versions_json"]) if isinstance(img["model_versions_json"], str) else img["model_versions_json"]
            except Exception:
                model_versions = {}
        images.append({
            "id": img_id,
            "round_id": img.get("round_id") or round_row["id"],
            "parent_image_id": img.get("parent_image_id"),
            "variant_index": img.get("variant_index", 0),
            "kind": img.get("kind", "variant"),
            "width": img.get("width", 512),
            "height": img.get("height", 512),
            "seed": img.get("seed"),
            "variant_axes": variant_axes,
            "attr_adherence": img.get("attr_adherence"),
            "identity_similarity": img.get("identity_similarity"),
            "speculative": bool(img.get("speculative")),
            "is_final": bool(img.get("is_final")),
            "has_sketch": bool(img.get("sketch_path")),
            "urls": {
                "photo": f"/api/v1/images/{img_id}/file?style=photo",
                "pencil": f"/api/v1/images/{img_id}/file?style=pencil",
                "thumb": f"/api/v1/images/{img_id}/file?style=photo&size=thumb",
            },
            "model_versions": model_versions,
            "created_at": img.get("created_at") or round_row["created_at"],
        })

    params = {}
    if round_row.get("params_json"):
        try:
            params = json.loads(round_row["params_json"]) if isinstance(round_row["params_json"], str) else round_row["params_json"]
        except Exception:
            params = {}

    return {
        "id": round_row["id"],
        "session_id": round_row["session_id"],
        "round_no": round_row["round_no"],
        "kind": round_row["kind"],
        "status": round_row["status"],
        "params": params,
        "images": images,
        "error": round_row.get("error"),
        "created_at": round_row["created_at"],
        "finished_at": round_row.get("finished_at"),
    }


def insert_round_images(
    conn: Connection,
    images: list[dict[str, Any]],
    sid: str,
    round_id: str,
    now_iso: str,
):
    storage_base = Path(settings.STORAGE_DIR)
    for img in images:
        img_id = img.get("id") or str(uuid.uuid4())
        variant_idx = img.get("variant_index", 0)
        kind_val = img.get("kind", "variant")
        width_val = img.get("width", 512)
        height_val = img.get("height", 512)
        seed_val = img.get("seed")
        prompt_val = img.get("prompt_text", "")
        neg_prompt_val = img.get("negative_prompt", "")

        axes_val = img.get("variant_axes_json")
        if not axes_val:
            axes_val = json.dumps(img.get("variant_axes") or {})
        elif not isinstance(axes_val, str):
            axes_val = json.dumps(axes_val)

        mv_val = img.get("model_versions_json")
        if not mv_val:
            mv_val = json.dumps(img.get("model_versions") or {})
        elif not isinstance(mv_val, str):
            mv_val = json.dumps(mv_val)

        sha_val = img.get("sha256") or f"sha_{img_id}"
        skt_sha_val = img.get("sketch_sha256") or f"skt_sha_{img_id}"
        rel_img = img.get("storage_path") or f"images/{img_id}.png"
        rel_skt = img.get("sketch_path") or f"sketches/{img_id}.png"
        parent_img_id = img.get("parent_image_id")

        img_file = storage_base / rel_img
        if not img_file.exists():
            img_file.parent.mkdir(parents=True, exist_ok=True)
            img_file.write_bytes(MINIMAL_PNG_BYTES)

        skt_file = storage_base / rel_skt
        if not skt_file.exists():
            skt_file.parent.mkdir(parents=True, exist_ok=True)
            skt_file.write_bytes(MINIMAL_PNG_BYTES)

        conn.execute(
            text(
                """
                INSERT INTO images (
                    id, session_id, round_id, parent_image_id, variant_index, kind,
                    width, height, seed, prompt_text, negative_prompt, variant_axes_json,
                    sha256, sketch_sha256, storage_path, sketch_path, model_versions_json,
                    attr_adherence, identity_similarity, speculative, is_final, created_at
                ) VALUES (
                    :id, :session_id, :round_id, :parent_image_id, :variant_index, :kind,
                    :width, :height, :seed, :prompt_text, :negative_prompt, :variant_axes_json,
                    :sha256, :sketch_sha256, :storage_path, :sketch_path, :model_versions_json,
                    :attr_adherence, :identity_similarity, :speculative, :is_final, :created_at
                )
                """
            ),
            {
                "id": img_id,
                "session_id": sid,
                "round_id": round_id,
                "parent_image_id": parent_img_id,
                "variant_index": variant_idx,
                "kind": kind_val,
                "width": width_val,
                "height": height_val,
                "seed": seed_val,
                "prompt_text": prompt_val,
                "negative_prompt": neg_prompt_val,
                "variant_axes_json": axes_val,
                "sha256": sha_val,
                "sketch_sha256": skt_sha_val,
                "storage_path": rel_img,
                "sketch_path": rel_skt,
                "model_versions_json": mv_val,
                "attr_adherence": img.get("attr_adherence"),
                "identity_similarity": img.get("identity_similarity"),
                "speculative": int(img.get("speculative", 0)),
                "is_final": int(img.get("is_final", 0)),
                "created_at": now_iso,
            },
        )


@router.post("/sessions/{sid}/rounds/generate", status_code=201)
@router.post("/sessions/{sid}/rounds", status_code=201)
def generate_round(
    sid: str,
    body: RoundGenerateRequest,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Cannot generate rounds for a completed session", status_code=400)

    snap_id = session_dict.get("current_snapshot_id")
    current_attrs: dict[str, Any] = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}
    if snap_id:
        snap_row = conn.execute(
            text("SELECT attributes_json FROM attribute_snapshots WHERE id = :snap_id"),
            {"snap_id": snap_id},
        ).fetchone()
        if snap_row and snap_row[0]:
            try:
                current_attrs = json.loads(snap_row[0])
            except Exception:
                current_attrs = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}

    locked_features = []
    if session_dict.get("locked_features_json"):
        try:
            locked_features = json.loads(session_dict["locked_features_json"])
        except Exception:
            locked_features = []

    max_round = conn.execute(
        text("SELECT MAX(round_no) FROM rounds WHERE session_id = :sid"),
        {"sid": sid},
    ).scalar()
    new_round_no = (max_round or 0) + 1
    round_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()

    # Call ML Service
    images = ml_proxy.generate_initial_round(
        session_id=sid,
        round_id=round_id,
        round_no=new_round_no,
        attributes=current_attrs,
        locked_features=locked_features,
        num_variants=body.num_variants,
        seed=body.seed,
        axes=body.axes,
    )

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO rounds (
                    id, session_id, round_no, kind, params_json, attribute_snapshot_id,
                    status, created_by, created_at, finished_at
                ) VALUES (
                    :id, :session_id, :round_no, 'initial', :params_json, :snapshot_id,
                    'done', :created_by, :created_at, :finished_at
                )
                """
            ),
            {
                "id": round_id,
                "session_id": sid,
                "round_no": new_round_no,
                "params_json": json.dumps({"num_variants": body.num_variants, "seed": body.seed, "axes": body.axes}),
                "snapshot_id": snap_id,
                "created_by": user["id"],
                "created_at": now_iso,
                "finished_at": now_iso,
            },
        )
        insert_round_images(conn, images, sid, round_id, now_iso)
        conn.execute(
            text("UPDATE sessions SET current_round = :rnd, updated_at = :now WHERE id = :sid"),
            {"rnd": new_round_no, "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="round.generate",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="round",
            resource_id=round_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={
                "session_id": sid,
                "round_no": new_round_no,
                "kind": "initial",
                "num_variants": len(images),
            },
        )

    round_row = {
        "id": round_id,
        "session_id": sid,
        "round_no": new_round_no,
        "kind": "initial",
        "status": "done",
        "params_json": json.dumps({"num_variants": body.num_variants, "seed": body.seed, "axes": body.axes}),
        "error": None,
        "created_at": now_iso,
        "finished_at": now_iso,
    }
    return format_round_dict(round_row, images)


@router.post("/sessions/{sid}/rounds/evolve", status_code=201)
def evolve_round(
    sid: str,
    body: RoundEvolveRequest,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Cannot evolve rounds for a completed session", status_code=400)

    parent_round_id = body.parent_round_id
    if not parent_round_id:
        parent_row = conn.execute(
            text("SELECT id FROM rounds WHERE session_id = :sid ORDER BY round_no DESC LIMIT 1"),
            {"sid": sid},
        ).fetchone()
        if not parent_row:
            raise AppError("VALIDATION_ERROR", "No parent round available to evolve from", status_code=400)
        parent_round_id = parent_row[0]

    snap_id = session_dict.get("current_snapshot_id")
    current_attrs: dict[str, Any] = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}
    if snap_id:
        snap_row = conn.execute(
            text("SELECT attributes_json FROM attribute_snapshots WHERE id = :snap_id"),
            {"snap_id": snap_id},
        ).fetchone()
        if snap_row and snap_row[0]:
            try:
                current_attrs = json.loads(snap_row[0])
            except Exception:
                pass

    locked_features = []
    if session_dict.get("locked_features_json"):
        try:
            locked_features = json.loads(session_dict["locked_features_json"])
        except Exception:
            pass

    max_round = conn.execute(
        text("SELECT MAX(round_no) FROM rounds WHERE session_id = :sid"),
        {"sid": sid},
    ).scalar()
    new_round_no = (max_round or 0) + 1
    round_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()

    images = ml_proxy.evolve_round(
        session_id=sid,
        round_id=round_id,
        round_no=new_round_no,
        parent_round_id=parent_round_id,
        feedback=body.feedback,
        attributes=current_attrs,
        locked_features=locked_features,
        num_variants=body.num_variants,
    )

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO rounds (
                    id, session_id, round_no, kind, params_json, attribute_snapshot_id,
                    status, created_by, created_at, finished_at
                ) VALUES (
                    :id, :session_id, :round_no, 'evolve', :params_json, :snapshot_id,
                    'done', :created_by, :created_at, :finished_at
                )
                """
            ),
            {
                "id": round_id,
                "session_id": sid,
                "round_no": new_round_no,
                "params_json": json.dumps({"parent_round_id": parent_round_id, "feedback": body.feedback, "num_variants": body.num_variants}),
                "snapshot_id": snap_id,
                "created_by": user["id"],
                "created_at": now_iso,
                "finished_at": now_iso,
            },
        )
        insert_round_images(conn, images, sid, round_id, now_iso)
        conn.execute(
            text("UPDATE sessions SET current_round = :rnd, updated_at = :now WHERE id = :sid"),
            {"rnd": new_round_no, "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="round.evolve",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="round",
            resource_id=round_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={
                "session_id": sid,
                "round_no": new_round_no,
                "kind": "evolve",
                "num_variants": len(images),
            },
        )

    round_row = {
        "id": round_id,
        "session_id": sid,
        "round_no": new_round_no,
        "kind": "evolve",
        "status": "done",
        "params_json": json.dumps({"parent_round_id": parent_round_id, "feedback": body.feedback, "num_variants": body.num_variants}),
        "error": None,
        "created_at": now_iso,
        "finished_at": now_iso,
    }
    return format_round_dict(round_row, images)


@router.post("/sessions/{sid}/rounds/edit", status_code=201)
def edit_round(
    sid: str,
    body: RoundEditRequest,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Cannot edit rounds for a completed session", status_code=400)

    parent_img = conn.execute(
        text("SELECT id, round_id FROM images WHERE id = :pid AND session_id = :sid"),
        {"pid": body.parent_image_id, "sid": sid},
    ).fetchone()
    if not parent_img:
        raise AppError("NOT_FOUND", f"Parent image '{body.parent_image_id}' not found in session", status_code=404)

    snap_id = session_dict.get("current_snapshot_id")
    max_round = conn.execute(
        text("SELECT MAX(round_no) FROM rounds WHERE session_id = :sid"),
        {"sid": sid},
    ).scalar()
    new_round_no = (max_round or 0) + 1
    round_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()

    images = ml_proxy.edit_round(
        session_id=sid,
        round_id=round_id,
        round_no=new_round_no,
        parent_image_id=body.parent_image_id,
        instruction_text=body.instruction_text,
        kind=body.kind,
        region=body.region,
        mask_b64=body.mask_b64,
    )

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO rounds (
                    id, session_id, round_no, kind, params_json, attribute_snapshot_id,
                    status, created_by, created_at, finished_at
                ) VALUES (
                    :id, :session_id, :round_no, :kind, :params_json, :snapshot_id,
                    'done', :created_by, :created_at, :finished_at
                )
                """
            ),
            {
                "id": round_id,
                "session_id": sid,
                "round_no": new_round_no,
                "kind": body.kind,
                "params_json": json.dumps({"parent_image_id": body.parent_image_id, "instruction_text": body.instruction_text}),
                "snapshot_id": snap_id,
                "created_by": user["id"],
                "created_at": now_iso,
                "finished_at": now_iso,
            },
        )
        insert_round_images(conn, images, sid, round_id, now_iso)
        conn.execute(
            text("UPDATE sessions SET current_round = :rnd, updated_at = :now WHERE id = :sid"),
            {"rnd": new_round_no, "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="round.edit",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="round",
            resource_id=round_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={
                "session_id": sid,
                "round_no": new_round_no,
                "kind": body.kind,
                "parent_image_id": body.parent_image_id,
            },
        )

    round_row = {
        "id": round_id,
        "session_id": sid,
        "round_no": new_round_no,
        "kind": body.kind,
        "status": "done",
        "params_json": json.dumps({"parent_image_id": body.parent_image_id, "instruction_text": body.instruction_text}),
        "error": None,
        "created_at": now_iso,
        "finished_at": now_iso,
    }
    return format_round_dict(round_row, images)


@router.get("/sessions/{sid}/rounds")
def list_session_rounds(
    sid: str,
    session_access_info: dict = Depends(require_session_access("view")),
    conn: Connection = Depends(get_connection),
):
    rounds_rows = conn.execute(
        text("SELECT * FROM rounds WHERE session_id = :sid ORDER BY round_no ASC"),
        {"sid": sid},
    ).mappings().fetchall()

    result = []
    for r_row in rounds_rows:
        imgs = conn.execute(
            text("SELECT * FROM images WHERE round_id = :rid ORDER BY variant_index ASC"),
            {"rid": r_row["id"]},
        ).mappings().fetchall()
        result.append(format_round_dict(dict(r_row), [dict(i) for i in imgs]))
    return result


@router.get("/sessions/{sid}/rounds/{round_id}")
def get_session_round(
    sid: str,
    round_id: str,
    session_access_info: dict = Depends(require_session_access("view")),
    conn: Connection = Depends(get_connection),
):
    r_row = conn.execute(
        text("SELECT * FROM rounds WHERE id = :rid AND session_id = :sid"),
        {"rid": round_id, "sid": sid},
    ).mappings().fetchone()
    if not r_row:
        raise AppError("NOT_FOUND", f"Round '{round_id}' not found", status_code=404)

    imgs = conn.execute(
        text("SELECT * FROM images WHERE round_id = :rid ORDER BY variant_index ASC"),
        {"rid": round_id},
    ).mappings().fetchall()
    return format_round_dict(dict(r_row), [dict(i) for i in imgs])


@router.get("/images/{image_id}/file")
def get_image_file(
    image_id: str,
    style: str = "photo",
    size: str = "full",
    conn: Connection = Depends(get_connection),
):
    img_row = conn.execute(
        text("SELECT storage_path, sketch_path FROM images WHERE id = :iid"),
        {"iid": image_id},
    ).mappings().fetchone()
    if not img_row:
        raise AppError("NOT_FOUND", f"Image '{image_id}' not found", status_code=404)

    storage_base = Path(settings.STORAGE_DIR)
    rel = img_row["sketch_path"] if style == "pencil" and img_row["sketch_path"] else img_row["storage_path"]
    file_path = storage_base / rel

    if not file_path.exists():
        alt_path = Path(rel)
        if alt_path.exists():
            file_path = alt_path
        else:
            raise AppError("NOT_FOUND", "Image file not found on disk", status_code=404)

    return FileResponse(file_path, media_type="image/png")


DISCLAIMER_V1 = "AI-generated investigative aid — not a photograph, not evidence of identity."


class FeedbackCreate(BaseModel):
    round_id: str | None = None
    image_id: str | None = None
    event_type: str = Field(..., pattern="^(pick|reject|more_like|less_like|edit_request|lock_feature|unlock_feature|confidence_set|undo)$")
    payload: dict[str, Any] = Field(default_factory=dict)


class LocksUpdate(BaseModel):
    locked_features: list[str] = Field(default_factory=list)


class SessionFinalize(BaseModel):
    image_id: str
    notes: str | None = None


@router.post("/sessions/{sid}/feedback", status_code=201)
def record_feedback(
    sid: str,
    body: FeedbackCreate,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Cannot record feedback for a completed session", status_code=400)

    # Validate image if provided
    if body.image_id:
        img_row = conn.execute(
            text("SELECT id FROM images WHERE id = :iid AND session_id = :sid"),
            {"iid": body.image_id, "sid": sid},
        ).fetchone()
        if not img_row:
            raise AppError("NOT_FOUND", f"Image '{body.image_id}' not found in session", status_code=404)

    # Validate round if provided
    if body.round_id:
        rnd_row = conn.execute(
            text("SELECT id FROM rounds WHERE id = :rid AND session_id = :sid"),
            {"rid": body.round_id, "sid": sid},
        ).fetchone()
        if not rnd_row:
            raise AppError("NOT_FOUND", f"Round '{body.round_id}' not found in session", status_code=404)

    event_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()

    current_locked = []
    if session_dict.get("locked_features_json"):
        try:
            current_locked = json.loads(session_dict["locked_features_json"])
        except Exception:
            current_locked = []

    new_selected_img = session_dict.get("selected_image_id")
    new_locked = list(current_locked)

    if body.event_type == "pick" and body.image_id:
        new_selected_img = body.image_id
    elif body.event_type == "lock_feature":
        feat = body.payload.get("feature") or body.payload.get("key")
        if feat and feat not in new_locked:
            new_locked.append(feat)
    elif body.event_type == "unlock_feature":
        feat = body.payload.get("feature") or body.payload.get("key")
        if feat and feat in new_locked:
            new_locked.remove(feat)

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO feedback_events (
                    id, session_id, round_id, image_id, event_type, payload_json, created_by, created_at
                ) VALUES (
                    :id, :session_id, :round_id, :image_id, :event_type, :payload_json, :created_by, :created_at
                )
                """
            ),
            {
                "id": event_id,
                "session_id": sid,
                "round_id": body.round_id,
                "image_id": body.image_id,
                "event_type": body.event_type,
                "payload_json": json.dumps(body.payload),
                "created_by": user["id"],
                "created_at": now_iso,
            },
        )
        conn.execute(
            text(
                """
                UPDATE sessions
                SET selected_image_id = :sel_img,
                    locked_features_json = :lj,
                    updated_at = :now
                WHERE id = :sid
                """
            ),
            {
                "sel_img": new_selected_img,
                "lj": json.dumps(new_locked),
                "now": now_iso,
                "sid": sid,
            },
        )
        write_audit_entry(
            conn,
            action="feedback.create",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="feedback_event",
            resource_id=event_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={
                "session_id": sid,
                "event_type": body.event_type,
                "image_id": body.image_id,
                "round_id": body.round_id,
            },
        )

    return {
        "id": event_id,
        "session_id": sid,
        "round_id": body.round_id,
        "image_id": body.image_id,
        "event_type": body.event_type,
        "payload": body.payload,
        "created_by": user["id"],
        "created_at": now_iso,
    }


@router.get("/sessions/{sid}/feedback")
def list_session_feedback(
    sid: str,
    session_access_info: dict = Depends(require_session_access("view")),
    conn: Connection = Depends(get_connection),
):
    rows = conn.execute(
        text("SELECT * FROM feedback_events WHERE session_id = :sid ORDER BY created_at ASC"),
        {"sid": sid},
    ).mappings().fetchall()

    results = []
    for r in rows:
        p = {}
        if r.get("payload_json"):
            try:
                p = json.loads(r["payload_json"])
            except Exception:
                p = {}
        results.append({
            "id": r["id"],
            "session_id": r["session_id"],
            "round_id": r["round_id"],
            "image_id": r["image_id"],
            "event_type": r["event_type"],
            "payload": p,
            "created_by": r["created_by"],
            "created_at": r["created_at"],
        })
    return results


@router.put("/sessions/{sid}/locks")
def update_session_locks(
    sid: str,
    body: LocksUpdate,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Cannot update locks for a completed session", status_code=400)

    now_iso = datetime.now(UTC).isoformat()
    with atomic_mutation(conn):
        conn.execute(
            text("UPDATE sessions SET locked_features_json = :lj, updated_at = :now WHERE id = :sid"),
            {"lj": json.dumps(body.locked_features), "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="attributes.update",
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
            details={"subaction": "locks.update", "locked_features": body.locked_features},
        )

    return {"session_id": sid, "locked_features": body.locked_features}


@router.post("/sessions/{sid}/undo")
def undo_session_round(
    sid: str,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Cannot undo in a completed session", status_code=400)

    latest_round = conn.execute(
        text("SELECT id, round_no, kind FROM rounds WHERE session_id = :sid ORDER BY round_no DESC LIMIT 1"),
        {"sid": sid},
    ).mappings().fetchone()

    if not latest_round:
        raise AppError("VALIDATION_ERROR", "No rounds to undo in this session", status_code=400)

    undone_rid = latest_round["id"]
    undone_round_no = latest_round["round_no"]
    new_round_no = max(0, undone_round_no - 1)
    now_iso = datetime.now(UTC).isoformat()
    undo_event_id = str(uuid.uuid4())

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                DELETE FROM feedback_events
                WHERE round_id = :rid OR image_id IN (SELECT id FROM images WHERE round_id = :rid)
                """
            ),
            {"rid": undone_rid},
        )
        conn.execute(text("UPDATE images SET parent_image_id = NULL WHERE round_id = :rid"), {"rid": undone_rid})
        conn.execute(text("DELETE FROM images WHERE round_id = :rid"), {"rid": undone_rid})
        conn.execute(text("DELETE FROM rounds WHERE id = :rid"), {"rid": undone_rid})

        selected_img = session_dict.get("selected_image_id")
        if selected_img:
            still_exists = conn.execute(text("SELECT id FROM images WHERE id = :iid"), {"iid": selected_img}).fetchone()
            if not still_exists:
                selected_img = None

        conn.execute(
            text(
                """
                UPDATE sessions
                SET current_round = :rnd,
                    selected_image_id = :sel_img,
                    updated_at = :now
                WHERE id = :sid
                """
            ),
            {"rnd": new_round_no, "sel_img": selected_img, "now": now_iso, "sid": sid},
        )

        conn.execute(
            text(
                """
                INSERT INTO feedback_events (
                    id, session_id, round_id, image_id, event_type, payload_json, created_by, created_at
                ) VALUES (
                    :id, :session_id, NULL, NULL, 'undo', :payload_json, :created_by, :created_at
                )
                """
            ),
            {
                "id": undo_event_id,
                "session_id": sid,
                "payload_json": json.dumps({"undone_round_id": undone_rid, "undone_round_no": undone_round_no}),
                "created_by": user["id"],
                "created_at": now_iso,
            },
        )

        write_audit_entry(
            conn,
            action="feedback.create",
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            resource_type="feedback_event",
            resource_id=undo_event_id,
            case_id=case_id,
            purpose=purpose,
            ip=client_ip,
            user_agent=user_agent,
            status_code=200,
            details={"event_type": "undo", "undone_round_id": undone_rid, "undone_round_no": undone_round_no, "new_round_no": new_round_no},
        )

    updated_session = conn.execute(text("SELECT * FROM sessions WHERE id = :sid"), {"sid": sid}).mappings().fetchone()
    return assemble_session_state(conn, dict(updated_session))


@router.post("/sessions/{sid}/finalize")
def finalize_session(
    sid: str,
    body: SessionFinalize,
    request: Request,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    user = session_access_info["user"]
    purpose = session_access_info["purpose"]
    case_id = session_dict["case_id"]
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if session_dict.get("status") == "completed":
        raise AppError("VALIDATION_ERROR", "Session is already completed", status_code=400)

    img_row = conn.execute(
        text("SELECT * FROM images WHERE id = :iid AND session_id = :sid"),
        {"iid": body.image_id, "sid": sid},
    ).mappings().fetchone()
    if not img_row:
        raise AppError("NOT_FOUND", f"Image '{body.image_id}' not found in session", status_code=404)

    max_round = conn.execute(
        text("SELECT MAX(round_no) FROM rounds WHERE session_id = :sid"),
        {"sid": sid},
    ).scalar()
    new_round_no = (max_round or 0) + 1
    round_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO rounds (
                    id, session_id, round_no, kind, params_json, attribute_snapshot_id,
                    status, created_by, created_at, finished_at
                ) VALUES (
                    :id, :session_id, :round_no, 'finalize', :params_json, :snapshot_id,
                    'done', :created_by, :created_at, :finished_at
                )
                """
            ),
            {
                "id": round_id,
                "session_id": sid,
                "round_no": new_round_no,
                "params_json": json.dumps({"final_image_id": body.image_id, "notes": body.notes}),
                "snapshot_id": session_dict.get("current_snapshot_id"),
                "created_by": user["id"],
                "created_at": now_iso,
                "finished_at": now_iso,
            },
        )
        conn.execute(text("UPDATE images SET is_final = 1 WHERE id = :iid"), {"iid": body.image_id})
        conn.execute(
            text(
                """
                UPDATE sessions
                SET status = 'completed',
                    selected_image_id = :iid,
                    current_round = :rnd,
                    updated_at = :now
                WHERE id = :sid
                """
            ),
            {"iid": body.image_id, "rnd": new_round_no, "now": now_iso, "sid": sid},
        )
        write_audit_entry(
            conn,
            action="session.finalize",
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
            details={"final_image_id": body.image_id, "notes": body.notes, "round_no": new_round_no},
        )

    return {
        "session_id": sid,
        "status": "completed",
        "final_image_id": body.image_id,
        "round_no": new_round_no,
        "disclaimer": DISCLAIMER_V1,
        "notes": body.notes,
        "finalized_at": now_iso,
    }


@router.get("/sessions/{sid}/next-question")
def get_next_question(
    sid: str,
    session_access_info: dict = Depends(require_session_access("view")),
    conn: Connection = Depends(get_connection),
):
    session_dict = dict(session_access_info["session"])
    case_id = session_dict["case_id"]

    from backend.app.services.sessions import SALIENT_KEYS
    from backend.app.services.statement_pipeline import generate_next_question

    snap_id = session_dict.get("current_snapshot_id")
    current_attrs: dict[str, Any] = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}
    if snap_id:
        snap_row = conn.execute(
            text("SELECT attributes_json FROM attribute_snapshots WHERE id = :snap_id"),
            {"snap_id": snap_id},
        ).fetchone()
        if snap_row and snap_row[0]:
            try:
                current_attrs = json.loads(snap_row[0])
            except Exception:
                pass

    attr_map = current_attrs.get("attributes") or {}
    unspecified_keys = []
    target_key = None
    for k in SALIENT_KEYS:
        val = attr_map.get(k)
        if not val or val.get("value") is None:
            unspecified_keys.append(k)
            if target_key is None:
                target_key = k

    question_text = generate_next_question(current_attrs, case_id=case_id, session_id=sid)

    return {
        "session_id": sid,
        "next_question": question_text,
        "target_key": target_key or "other",
        "unspecified_keys": unspecified_keys,
    }


@router.get("/images/{image_id}")
def get_image_metadata(
    image_id: str,
    conn: Connection = Depends(get_connection),
):
    img_row = conn.execute(
        text("SELECT * FROM images WHERE id = :iid"),
        {"iid": image_id},
    ).mappings().fetchone()
    if not img_row:
        raise AppError("NOT_FOUND", f"Image '{image_id}' not found", status_code=404)

    img = dict(img_row)
    img_id = img["id"]
    variant_axes = {}
    if img.get("variant_axes_json"):
        try:
            variant_axes = json.loads(img["variant_axes_json"])
        except Exception:
            pass

    model_versions = {}
    if img.get("model_versions_json"):
        try:
            model_versions = json.loads(img["model_versions_json"])
        except Exception:
            pass

    return {
        "id": img_id,
        "session_id": img["session_id"],
        "round_id": img["round_id"],
        "parent_image_id": img.get("parent_image_id"),
        "variant_index": img["variant_index"],
        "kind": img["kind"],
        "width": img["width"],
        "height": img["height"],
        "seed": img.get("seed"),
        "variant_axes": variant_axes,
        "attr_adherence": img.get("attr_adherence"),
        "identity_similarity": img.get("identity_similarity"),
        "speculative": bool(img.get("speculative")),
        "is_final": bool(img.get("is_final")),
        "has_sketch": bool(img.get("sketch_path")),
        "urls": {
            "photo": f"/api/v1/images/{img_id}/file?style=photo",
            "pencil": f"/api/v1/images/{img_id}/file?style=pencil",
            "thumb": f"/api/v1/images/{img_id}/file?style=photo&size=thumb",
        },
        "model_versions": model_versions,
        "created_at": img["created_at"],
    }

