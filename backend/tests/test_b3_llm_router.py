import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Ensure required env vars are set
os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"
os.environ["SEED_PASSWORD_ADMIN"] = "admin_pass_123"
os.environ["SEED_PASSWORD_SUPERVISOR"] = "supervisor_pass_123"
os.environ["SEED_PASSWORD_INVESTIGATOR"] = "investigator_pass_123"
os.environ["SEED_PASSWORD_ARTIST"] = "artist_pass_123"
os.environ["SEED_PASSWORD_AUDITOR"] = "auditor_pass_123"

import scripts.init_db as init_db_script
import scripts.seed_users as seed_users_script
from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.core.security import create_access_token
from backend.app.db.session import get_connection, get_engine, set_engine
from backend.app.llm.guards import validate_and_guard_parse_delta
from backend.app.llm.router import (
    _llm_cache,
    complete,
    gemini_rate_limiter,
)
from backend.app.main import create_app

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="function")
def test_db(tmp_path):
    db_file = tmp_path / "test_velora_b3.db"
    init_db_script.init_db(db_file)
    seed_users_script.seed_users(db_file)
    db_url = f"sqlite:///{db_file}"

    test_engine = get_engine(db_url)
    set_engine(test_engine)

    # Seed one real case and one demo case
    real_case_id = str(uuid.uuid4())
    demo_case_id = str(uuid.uuid4())
    now_iso = "2026-10-28T12:00:00.000Z"

    with test_engine.begin() as conn:
        # Get admin user id
        admin_row = conn.execute(text("SELECT id FROM users WHERE username = 'admin'")).fetchone()
        admin_id = admin_row[0]

        conn.execute(
            text(
                """
                INSERT INTO cases (id, case_number, title, data_mode, status, default_appearance_group, created_by, created_at, updated_at)
                VALUES (:id, :num, :title, 'real', 'open', 'south_asian', :cb, :ca, :ua)
                """
            ),
            {"id": real_case_id, "num": "CASE-REAL-001", "title": "Real Case", "cb": admin_id, "ca": now_iso, "ua": now_iso},
        )
        conn.execute(
            text(
                """
                INSERT INTO cases (id, case_number, title, data_mode, status, default_appearance_group, created_by, created_at, updated_at)
                VALUES (:id, :num, :title, 'demo', 'open', 'south_asian', :cb, :ca, :ua)
                """
            ),
            {"id": demo_case_id, "num": "CASE-DEMO-001", "title": "Demo Case", "cb": admin_id, "ca": now_iso, "ua": now_iso},
        )

    def override_get_connection():
        with test_engine.connect() as conn:
            yield conn

    app = create_app()
    app.dependency_overrides[get_connection] = override_get_connection
    client = TestClient(app)

    # Clear router cache
    _llm_cache.clear()

    return {
        "client": client,
        "db_file": db_file,
        "engine": test_engine,
        "app": app,
        "real_case_id": real_case_id,
        "demo_case_id": demo_case_id,
    }


def _get_admin_token(test_db):
    with test_db["engine"].connect() as conn:
        row = conn.execute(text("SELECT id, username, role FROM users WHERE username = 'admin'")).fetchone()
    return create_access_token(sub=row[0], role=row[2])


def _get_investigator_token(test_db):
    with test_db["engine"].connect() as conn:
        row = conn.execute(text("SELECT id, username, role FROM users WHERE username = 'investigator'")).fetchone()
    return create_access_token(sub=row[0], role=row[2])


# ==============================================================================
# TB3.1: scripts/llm_smoke.py execution test
# ==============================================================================
def test_tb3_1_llm_smoke_script(test_db):
    """
    TB3.1: scripts/llm_smoke.py executes without crash and reports provider status.
    """
    from scripts import llm_smoke

    # Mock providers to succeed deterministically during script run
    with patch("scripts.llm_smoke.call_gemini", return_value=('{"status":"ok","provider":"gemini"}', 10, 10, 25)), \
         patch("scripts.llm_smoke.call_ollama", return_value=('{"status":"ok","provider":"ollama"}', 10, 10, 30)), \
         patch("backend.app.llm.router.call_gemini", return_value=('{"status":"ok","provider":"gemini"}', 10, 10, 25)):
        # Execute smoke script
        llm_smoke.main()


# ==============================================================================
# TB3.2: GET /health/llm-live endpoint
# ==============================================================================
def test_tb3_2_health_llm_live(test_db):
    """
    TB3.2: GET /api/v1/health/llm-live:
    - 401 unauthenticated
    - 403 non-admin
    - 200 admin with structured response containing gemini & ollama status
    """
    client = test_db["client"]

    with patch.object(settings, "GEMINI_API_KEY", "test_gemini_key_123"), \
         patch.object(settings, "OLLAMA_URL", "http://localhost:11434"), \
         patch("backend.app.routers.health.call_gemini", return_value=("pong", 5, 5, 42)), \
         patch("backend.app.routers.health.call_ollama", return_value=("pong", 5, 5, 28)):
        # 1. Unauthenticated -> 401
        resp_unauth = client.get("/api/v1/health/llm-live")
        assert resp_unauth.status_code == 401

        # 2. Non-admin (investigator) -> 403
        inv_token = _get_investigator_token(test_db)
        resp_inv = client.get("/api/v1/health/llm-live", headers={"Authorization": f"Bearer {inv_token}"})
        assert resp_inv.status_code == 403

        # 3. Admin -> 200 with structure
        admin_token = _get_admin_token(test_db)
        resp_admin = client.get("/api/v1/health/llm-live", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp_admin.status_code == 200
        data = resp_admin.json()
        assert "gemini" in data
        assert "ollama" in data
        assert data["gemini"]["ok"] is True
        assert data["gemini"]["latency_ms"] == 42
        assert data["ollama"]["ok"] is True
        assert data["ollama"]["latency_ms"] == 28


# ==============================================================================
# TB3.3: Probe set schema validity and accuracy
# ==============================================================================
def test_tb3_3_probe_set_validity():
    """
    TB3.3: Probe set contains at least 15 valid multilingual witness descriptions.
    """
    probe_path = ROOT_DIR / "backend" / "tests" / "fixtures" / "llm_probe_set.jsonl"
    assert probe_path.exists(), "Probe set fixture missing"

    items = []
    with open(probe_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    assert len(items) >= 15
    languages = {item["language"] for item in items}
    assert "en" in languages
    assert "ta" in languages
    assert "hi" in languages

    for item in items:
        assert "id" in item
        assert "statement" in item
        assert "expected_attributes" in item
        assert isinstance(item["expected_attributes"], dict)
        assert len(item["expected_attributes"]) > 0


# ==============================================================================
# TB3.4: Real-mode isolation (R11.4)
# ==============================================================================
def test_tb3_4_real_mode_isolation(test_db):
    """
    TB3.4: Real-mode cases (data_mode='real'):
    - Gemini client / call must NEVER be constructed or invoked.
    - Successfully calls Ollama with route_reason='real_local_only'.
    - If Ollama is down, raises LLM_UNAVAILABLE_LOCAL (503).
    - NEVER inserts any row with provider='gemini' into llm_calls.
    """
    real_case_id = test_db["real_case_id"]
    smoke_schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    # Mock Gemini to raise an assertion if called
    mock_gemini = MagicMock(side_effect=AssertionError("FATAL PRIVACY VIOLATION: Gemini called for real case!"))

    # 1. Successful Ollama call for real case
    mock_ollama = MagicMock(return_value=('{"status": "ok"}', 12, 10, 50))
    with patch("backend.app.llm.router.call_gemini", mock_gemini), \
         patch("backend.app.llm.router.call_ollama", mock_ollama):
        res = complete(
            task="parse",
            case_id=real_case_id,
            system="sys",
            user="user text",
            schema=smoke_schema,
        )
        assert res.provider == "ollama"
        assert res.route_reason == "real_local_only"
        assert mock_gemini.call_count == 0
        assert mock_ollama.call_count == 1

    # Verify DB: exactly 1 row with provider='ollama', 0 with provider='gemini'
    with test_db["engine"].connect() as conn:
        calls = conn.execute(text("SELECT provider, route_reason, status FROM llm_calls WHERE case_id = :cid"), {"cid": real_case_id}).fetchall()
        assert len(calls) == 1
        assert calls[0][0] == "ollama"
        assert calls[0][1] == "real_local_only"
        assert calls[0][2] == "ok"

        gemini_count = conn.execute(text("SELECT COUNT(*) FROM llm_calls WHERE provider = 'gemini' AND case_id = :cid"), {"cid": real_case_id}).scalar()
        assert gemini_count == 0

    # 2. Ollama down for real case -> LLM_UNAVAILABLE_LOCAL (503)
    mock_ollama_down = MagicMock(side_effect=ConnectionError("Failed to connect to localhost:11434"))
    with patch("backend.app.llm.router.call_gemini", mock_gemini), \
         patch("backend.app.llm.router.call_ollama", mock_ollama_down):
        with pytest.raises(AppError) as exc_info:
            complete(
                task="parse",
                case_id=real_case_id,
                system="sys",
                user="user text 2",
                schema=smoke_schema,
            )
        assert exc_info.value.code == "LLM_UNAVAILABLE_LOCAL"
        assert exc_info.value.status_code == 503
        assert mock_gemini.call_count == 0

    # Verify DB still has ZERO rows for provider='gemini'
    with test_db["engine"].connect() as conn:
        gemini_count = conn.execute(text("SELECT COUNT(*) FROM llm_calls WHERE provider = 'gemini' AND case_id = :cid"), {"cid": real_case_id}).scalar()
        assert gemini_count == 0


# ==============================================================================
# TB3.5: Demo fallback
# ==============================================================================
def test_tb3_5_demo_fallback(test_db):
    """
    TB3.5: In demo mode (auto), when Gemini fails, router falls back to Ollama
    with route_reason='fallback_after_error'.
    """
    demo_case_id = test_db["demo_case_id"]
    smoke_schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    mock_gemini = MagicMock(side_effect=RuntimeError("Gemini 500 Internal Error"))
    mock_ollama = MagicMock(return_value=('{"status": "ok"}', 15, 12, 60))

    with patch("backend.app.llm.router.call_gemini", mock_gemini), \
         patch("backend.app.llm.router.call_ollama", mock_ollama):
        res = complete(
            task="parse",
            case_id=demo_case_id,
            system="sys",
            user="demo text",
            schema=smoke_schema,
        )
        assert res.provider == "ollama"
        assert res.route_reason == "fallback_after_error"
        assert mock_gemini.call_count == 1
        assert mock_ollama.call_count == 1

    # Verify DB ledger records: Gemini error row + Ollama ok row
    with test_db["engine"].connect() as conn:
        rows = conn.execute(text("SELECT provider, status, route_reason FROM llm_calls WHERE case_id = :cid ORDER BY created_at ASC"), {"cid": demo_case_id}).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "gemini" and rows[0][1] == "error"
        assert rows[1][0] == "ollama" and rows[1][1] == "ok" and rows[1][2] == "fallback_after_error"


# ==============================================================================
# TB3.6: Rate limiter burst overflow
# ==============================================================================
def test_tb3_6_gemini_burst_rate_limit(test_db):
    """
    TB3.6: When Gemini token bucket cannot acquire a token within 2s,
    it falls back to Ollama with route_reason='fallback_after_error'.
    """
    demo_case_id = test_db["demo_case_id"]
    smoke_schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    mock_gemini = MagicMock()
    mock_ollama = MagicMock(return_value=('{"status": "ok"}', 8, 8, 45))

    with patch.object(gemini_rate_limiter, "acquire", return_value=False), \
         patch("backend.app.llm.router.call_gemini", mock_gemini), \
         patch("backend.app.llm.router.call_ollama", mock_ollama):
        res = complete(
            task="question",
            case_id=demo_case_id,
            system="sys",
            user="burst question",
            schema=smoke_schema,
        )
        assert res.provider == "ollama"
        assert res.route_reason == "fallback_after_error"
        assert mock_gemini.call_count == 0
        assert mock_ollama.call_count == 1


# ==============================================================================
# TB3.7: In-memory caching
# ==============================================================================
def test_tb3_7_caching(test_db):
    """
    TB3.7: Identical queries for cacheable tasks return cached results (<50ms).
    Both calls record an entry in llm_calls ledger.
    """
    demo_case_id = test_db["demo_case_id"]
    smoke_schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    mock_gemini = MagicMock(return_value=('{"status": "ok"}', 20, 10, 150))

    with patch("backend.app.llm.router.call_gemini", mock_gemini):
        # 1st call: Cache miss
        res1 = complete(
            task="parse",
            case_id=demo_case_id,
            system="sys",
            user="identical query",
            schema=smoke_schema,
        )
        assert res1.cached is False
        assert mock_gemini.call_count == 1

        # 2nd call: Cache hit
        res2 = complete(
            task="parse",
            case_id=demo_case_id,
            system="sys",
            user="identical query",
            schema=smoke_schema,
        )
        assert res2.cached is True
        assert res2.latency_ms < 50
        assert mock_gemini.call_count == 1  # Provider was NOT invoked again

    # Both calls recorded in DB
    with test_db["engine"].connect() as conn:
        rows = conn.execute(text("SELECT id, status FROM llm_calls WHERE case_id = :cid"), {"cid": demo_case_id}).fetchall()
        assert len(rows) == 2
        assert rows[0][1] == "ok"
        assert rows[1][1] == "ok"


# ==============================================================================
# TB3.8: Guards unit tests
# ==============================================================================
def test_tb3_8_guards():
    """
    TB3.8: Guards enforce enum whitelisting, explicit appearance/skin tone words,
    and drop invalid inferred sources.
    """
    # 1. Unstated appearance_group and skin_tone dropped
    statement1 = "The suspect was around 30 years old with an oval face and curly hair."
    delta1 = {
        "attributes": {
            "appearance_group": {"value": "south_asian", "source": "stated"},
            "skin_tone": {"value": "wheatish", "source": "stated"},
            "face_shape": {"value": "oval", "source": "stated"},
        }
    }
    guarded1, dropped1 = validate_and_guard_parse_delta(delta1, statement1)
    assert "face_shape" in guarded1["attributes"]
    assert "appearance_group" not in guarded1["attributes"]
    assert "skin_tone" not in guarded1["attributes"]
    assert len(dropped1) == 2

    # 2. Explicit appearance_group and skin_tone words present -> kept
    statement2 = "The suspect was a wheatish south asian man with an oval face."
    delta2 = {
        "attributes": {
            "appearance_group": {"value": "south_asian", "source": "stated"},
            "skin_tone": {"value": "wheatish", "source": "stated"},
            "face_shape": {"value": "oval", "source": "stated"},
        }
    }
    guarded2, dropped2 = validate_and_guard_parse_delta(delta2, statement2)
    assert "appearance_group" in guarded2["attributes"]
    assert "skin_tone" in guarded2["attributes"]
    assert len(dropped2) == 0

    # 3. Enum whitelist rejection
    delta3 = {
        "attributes": {
            "chin": {"value": "super_sharp_extra", "source": "stated"},
        }
    }
    guarded3, dropped3 = validate_and_guard_parse_delta(delta3, statement2)
    assert "chin" not in guarded3["attributes"]
    assert len(dropped3) == 1
    assert "Invalid enum value" in dropped3[0]["reason"]

    # 4. Inferred source rejection on prohibited key
    delta4 = {
        "attributes": {
            "face_shape": {"value": "oval", "source": "inferred"},
            "sex_presentation": {"value": "male", "source": "inferred"},
        }
    }
    guarded4, dropped4 = validate_and_guard_parse_delta(delta4, statement2)
    assert "face_shape" not in guarded4["attributes"]
    assert "sex_presentation" in guarded4["attributes"]  # Inferred is allowed on sex_presentation
    assert len(dropped4) == 1


# ==============================================================================
# TB3.9: Schema repair (exactly 1 repair call)
# ==============================================================================
def test_tb3_9_schema_repair(test_db):
    """
    TB3.9: Schema validation invalid output triggers exactly 1 repair attempt.
    """
    demo_case_id = test_db["demo_case_id"]
    smoke_schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    # First return invalid schema, second return valid schema
    invalid_schema_json = '{"wrong_key": 123}'
    valid_schema_json = '{"status": "repaired_ok"}'

    call_sequence = [
        (invalid_schema_json, 10, 5, 50),
        (valid_schema_json, 15, 8, 40),
    ]

    mock_gemini = MagicMock(side_effect=call_sequence)

    with patch("backend.app.llm.router.call_gemini", mock_gemini):
        res = complete(
            task="translate",
            case_id=demo_case_id,
            system="sys",
            user="user text",
            schema=smoke_schema,
        )
        assert res.content == {"status": "repaired_ok"}
        assert mock_gemini.call_count == 2

    # Verify DB: 1st row has status='schema_invalid', 2nd row has status='ok'
    with test_db["engine"].connect() as conn:
        rows = conn.execute(text("SELECT status, error FROM llm_calls WHERE case_id = :cid ORDER BY created_at ASC"), {"cid": demo_case_id}).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "schema_invalid"
        assert rows[1][0] == "ok"


# ==============================================================================
# Task & case_id validation tests
# ==============================================================================
def test_no_case_scoping_rules(test_db):
    """
    case_id=None is allowed ONLY for smoke, synth_describe, glossary_suggest, translate.
    Any other task raises 422 VALIDATION_ERROR.
    """
    smoke_schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    # 1. Disallowed task without case_id -> VALIDATION_ERROR (422)
    with pytest.raises(AppError) as exc_info:
        complete(task="parse", case_id=None, system="", user="test", schema=smoke_schema)
    assert exc_info.value.code == "VALIDATION_ERROR"
    assert exc_info.value.status_code == 422

    # 2. Allowed task without case_id -> succeeds
    with patch("backend.app.llm.router.call_gemini", return_value=('{"status":"ok"}', 5, 5, 20)):
        res = complete(task="smoke", case_id=None, system="", user="test", schema=smoke_schema)
        assert res.content == {"status": "ok"}
