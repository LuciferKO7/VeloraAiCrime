import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from backend.app.audit.chain import write_audit_entry
from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.db.session import atomic_mutation, get_engine

logger = logging.getLogger("velora.registry_sync")

REQUIRED_ROLES = (
    "image_gen",
    "inpaint",
    "identity_adapter",
    "face_parser",
    "face_embedder",
    "upscaler",
    "attribute_verifier",
    "preference_model",
    "llm_parser",
    "asr",
    "translator",
    "prompt_lexicon",
    "glossary",
)


def sync_model_registry(engine_or_conn: Engine | Connection | None = None) -> list[dict[str, Any]]:
    """
    Synchronizes discovered models into model_registry (§8.0, Step B12).
    Discovers models from actual configuration and available services.
    Idempotent: updates existing rows and inserts new ones without duplicate entries.
    Never marks unavailable models as live.
    """
    now_iso = datetime.now(UTC).isoformat()
    discovered_models: list[dict[str, Any]] = []

    # 1. Local / Hub configured models
    # A. Built-in Prompt Lexicon
    discovered_models.append(
        {
            "name": "velora_feature_lexicon",
            "role": "prompt_lexicon",
            "version": "1.0",
            "source": "velora_builtin",
            "license": "Apache-2.0",
            "checksum": None,
            "metrics": {"total_attributes": 30},
            "is_active": 1,
        }
    )

    # B. Governed Glossary
    discovered_models.append(
        {
            "name": "approved_glossary",
            "role": "glossary",
            "version": "1.0",
            "source": "velora_governed",
            "license": "Internal",
            "checksum": None,
            "metrics": {"governance": "supervisor_approved"},
            "is_active": 1,
        }
    )

    # C. LLM Parser models (Ollama and/or Gemini)
    ollama_active = 0
    if settings.OLLAMA_URL:
        # Check if Ollama is actually reachable
        try:
            with httpx.Client(timeout=1.0) as client:
                r = client.get(f"{settings.OLLAMA_URL}/api/version")
                if r.status_code == 200:
                    ollama_active = 1
        except Exception:
            ollama_active = 0

        ollama_model_name = settings.OLLAMA_MODEL or "qwen2.5:3b-instruct"
        discovered_models.append(
            {
                "name": ollama_model_name,
                "role": "llm_parser",
                "version": "1.0",
                "source": "ollama",
                "license": "Open Weights",
                "checksum": None,
                "metrics": {"runtime": "local_ollama", "reachable": ollama_active},
                "is_active": ollama_active,
            }
        )

    if settings.GEMINI_API_KEY:
        gemini_model_name = settings.GEMINI_MODEL_FAST or "gemini-2.5-flash"
        # Only activate Gemini if Ollama is not active
        gemini_active = 1 if (not ollama_active) else 0
        discovered_models.append(
            {
                "name": gemini_model_name,
                "role": "llm_parser",
                "version": "1.0",
                "source": "google_gemini",
                "license": "Proprietary / API",
                "checksum": None,
                "metrics": {"provider": "gemini_free_tier"},
                "is_active": gemini_active,
            }
        )

    # 2. Query ML Service Manifest if reachable (§8.0, §12)
    ml_url = getattr(settings, "ML_SERVICE_URL", "http://localhost:8001")
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get(f"{ml_url}/ml/v1/manifest", headers={"X-Service-Key": settings.SERVICE_KEY})
            if resp.status_code == 200:
                data = resp.json()
                ml_models = data if isinstance(data, list) else data.get("models", [])
                for m in ml_models:
                    if m.get("role") in REQUIRED_ROLES:
                        discovered_models.append(
                            {
                                "name": m.get("name"),
                                "role": m.get("role"),
                                "version": m.get("version", "1.0"),
                                "source": m.get("source", "ml_service"),
                                "license": m.get("license"),
                                "checksum": m.get("checksum"),
                                "metrics": m.get("metrics") or {},
                                "is_active": int(m.get("is_active", 1)),
                            }
                        )
    except Exception as exc:
        logger.debug("ML service manifest query skipped: %s", exc)

    # 3. Query Speech Service Manifest if reachable (§8.0, §12)
    speech_url = getattr(settings, "SPEECH_SERVICE_URL", "http://localhost:8002")
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get(f"{speech_url}/sp/v1/manifest", headers={"X-Service-Key": settings.SERVICE_KEY})
            if resp.status_code == 200:
                data = resp.json()
                sp_models = data if isinstance(data, list) else data.get("models", [])
                for m in sp_models:
                    if m.get("role") in REQUIRED_ROLES:
                        discovered_models.append(
                            {
                                "name": m.get("name"),
                                "role": m.get("role"),
                                "version": m.get("version", "1.0"),
                                "source": m.get("source", "speech_service"),
                                "license": m.get("license"),
                                "checksum": m.get("checksum"),
                                "metrics": m.get("metrics") or {},
                                "is_active": int(m.get("is_active", 1)),
                            }
                        )
    except Exception as exc:
        logger.debug("Speech service manifest query skipped: %s", exc)

    # 4. Upsert into database
    def do_sync(conn: Connection) -> None:
        for model in discovered_models:
            m_id = str(uuid.uuid4())
            m_name = model["name"]
            m_role = model["role"]
            m_version = model["version"]
            m_source = model.get("source")
            m_license = model.get("license")
            m_checksum = model.get("checksum")
            m_metrics = json.dumps(model.get("metrics") or {})
            m_active = int(model.get("is_active", 0))

            # Idempotent upsert by (name, version)
            conn.execute(
                text(
                    """
                    INSERT INTO model_registry (
                        id, name, role, version, source, license,
                        checksum, metrics_json, is_active, registered_at
                    )
                    VALUES (
                        :id, :name, :role, :version, :source, :license,
                        :checksum, :metrics_json, :is_active, :registered_at
                    )
                    ON CONFLICT(name, version) DO UPDATE SET
                        role = excluded.role,
                        source = COALESCE(excluded.source, model_registry.source),
                        license = COALESCE(excluded.license, model_registry.license),
                        checksum = COALESCE(excluded.checksum, model_registry.checksum)
                    """
                ),
                {
                    "id": m_id,
                    "name": m_name,
                    "role": m_role,
                    "version": m_version,
                    "source": m_source,
                    "license": m_license,
                    "checksum": m_checksum,
                    "metrics_json": m_metrics,
                    "is_active": m_active,
                    "registered_at": now_iso,
                },
            )

    if isinstance(engine_or_conn, Connection):
        with atomic_mutation(engine_or_conn):
            do_sync(engine_or_conn)
    else:
        eng = engine_or_conn or get_engine()
        with eng.connect() as conn:
            with atomic_mutation(conn):
                do_sync(conn)

    logger.info("Synchronized %d models in model_registry", len(discovered_models))
    return discovered_models


def activate_model_exclusive(conn: Connection, model_id: str, current_user: dict[str, Any]) -> dict[str, Any]:
    """
    Exclusively activates a model for its role (§8.0, §12 Step B12).
    In a single transaction, deactivates all other models for that role and activates the target model.
    Audits the mutation under 'admin.model_activate'.
    """
    row = conn.execute(
        text("SELECT id, name, role, version, is_active FROM model_registry WHERE id = :id"),
        {"id": model_id},
    ).mappings().fetchone()

    if not row:
        raise AppError("NOT_FOUND", f"Model '{model_id}' not found in registry", status_code=404)

    role = row["role"]
    name = row["name"]
    version = row["version"]

    with atomic_mutation(conn):
        # 1. Exclusive deactivation: deactivate all models for this role
        conn.execute(
            text("UPDATE model_registry SET is_active = 0 WHERE role = :role"),
            {"role": role},
        )

        # 2. Activate target model
        conn.execute(
            text("UPDATE model_registry SET is_active = 1 WHERE id = :id"),
            {"id": model_id},
        )

        # 3. Hash-chained audit entry
        write_audit_entry(
            conn,
            action="admin.model_activate",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="model_registry",
            resource_id=model_id,
            status_code=200,
            details={"name": name, "role": role, "version": version},
        )

    updated_row = conn.execute(
        text("SELECT id, name, role, version, is_active FROM model_registry WHERE id = :id"),
        {"id": model_id},
    ).mappings().fetchone()

    return dict(updated_row)
