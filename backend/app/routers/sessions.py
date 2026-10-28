import json
import uuid
from datetime import UTC, datetime
from typing import Any

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


class StatementCreate(BaseModel):
    text: str
    speaker: str = "witness"
    input_mode: str = "text"
    audio_sha256: str | None = None
    language: str | None = None


class AttributesUpdate(BaseModel):
    attributes: dict[str, Any]
    unmapped_notes: list[str] | None = None


@router.post("/sessions/{sid}/statements", status_code=201)
def submit_statement(
    request: Request,
    body: StatementCreate,
    session_access_info: dict = Depends(require_session_access("edit")),
    conn: Connection = Depends(get_connection),
):
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

