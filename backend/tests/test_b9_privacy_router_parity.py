import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

import pytest
from sqlalchemy import create_engine, text

from backend.app.core.config import settings

settings.SERVICE_KEY = os.environ["SERVICE_KEY"]
settings.JWT_SECRET = os.environ["JWT_SECRET"]

from backend.app.core.errors import AppError  # noqa: E402
from backend.app.core.security import hash_password  # noqa: E402
from backend.app.db.session import set_engine  # noqa: E402
from backend.app.llm.guards import validate_and_guard_parse_delta  # noqa: E402
from backend.app.llm.router import clear_cache, complete  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db(tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    import sqlite3
    schema_sql = (ROOT / "contracts/schema.sql").read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    con.executescript(schema_sql)

    now = "2026-10-28T12:00:00.000Z"
    uid = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO users (id, username, full_name, role, password_hash, is_active, failed_logins, created_at)
        VALUES (?, 'investigator1', 'Investigator One', 'investigator', ?, 1, 0, ?)
        """,
        (uid, hash_password("pass_inv_123"), now),
    )

    real_case_id = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO cases (id, case_number, title, data_mode, default_appearance_group, status, created_by, created_at, updated_at)
        VALUES (?, 'FIR-REAL-B9-01', 'Real Mode Case', 'real', 'unspecified', 'open', ?, ?, ?)
        """,
        (real_case_id, uid, now, now),
    )

    demo_case_id = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO cases (id, case_number, title, data_mode, default_appearance_group, status, created_by, created_at, updated_at)
        VALUES (?, 'FIR-DEMO-B9-01', 'Demo Mode Case', 'demo', 'unspecified', 'open', ?, ?, ?)
        """,
        (demo_case_id, uid, now, now),
    )

    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"timeout": 60})
    set_engine(engine)
    clear_cache()

    yield {
        "engine": engine,
        "real_case_id": real_case_id,
        "demo_case_id": demo_case_id,
        "user_id": uid,
    }

    engine.dispose()
    set_engine(None)
    clear_cache()
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass


def test_tb9_1_real_case_isolation(temp_db):
    """
    TB9.1: Real case + Gemini key configured:
    For cases.data_mode == 'real', LLM calls for parse, question, edit_parse, translate
    MUST route to Ollama only. Gemini must never be constructed or invoked.
    """
    engine = temp_db["engine"]
    real_case_id = temp_db["real_case_id"]

    # Configure Gemini API key in settings
    settings.GEMINI_API_KEY = "AIzaSy_fake_test_gemini_key_12345"
    settings.LLM_PROVIDER_MODE = "auto"

    mock_gemini = MagicMock(name="call_gemini")
    mock_ollama = MagicMock(name="call_ollama", return_value=('{"attributes":{"face_shape":{"value":"oval","source":"stated"}}}', 50, 20, 45))

    tasks = ["parse", "question", "edit_parse", "translate"]

    with patch("backend.app.llm.router.call_gemini", mock_gemini), \
         patch("backend.app.llm.router.call_ollama", mock_ollama):

        for t in tasks:
            clear_cache()
            res = complete(
                t,
                case_id=real_case_id,
                system="System prompt for task",
                user="User prompt text",
                schema={"type": "object"} if t in ("parse", "edit_parse") else None,
            )
            assert res.provider == "ollama"
            assert res.route_reason == "real_local_only"

    # Crucial assertion: Gemini was NEVER invoked
    assert mock_gemini.call_count == 0, "Security Invariant Violated: Gemini was invoked for a real case!"
    assert mock_ollama.call_count >= 4

    # Audit log verification: all records for this case are ollama and real_local_only
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT task, provider, route_reason, status FROM llm_calls WHERE case_id = :cid ORDER BY created_at ASC"),
            {"cid": real_case_id},
        ).fetchall()
        assert len(rows) == 4
        for r in rows:
            assert r[1] == "ollama"
            assert r[2] == "real_local_only"
            assert r[3] == "ok"


def test_tb9_2_real_case_fail_closed(temp_db):
    """
    TB9.2: Real case + Ollama unavailable / timeout:
    When local Ollama fails or times out in real mode, the request MUST fail closed
    with HTTP 503 LLM_UNAVAILABLE_LOCAL. Gemini must NEVER be called as fallback.
    """
    engine = temp_db["engine"]
    real_case_id = temp_db["real_case_id"]

    settings.GEMINI_API_KEY = "AIzaSy_fake_test_gemini_key_12345"
    mock_gemini = MagicMock(name="call_gemini")
    mock_ollama = MagicMock(name="call_ollama", side_effect=Exception("Failed to connect to Ollama on :11434"))

    with patch("backend.app.llm.router.call_gemini", mock_gemini), \
         patch("backend.app.llm.router.call_ollama", mock_ollama):

        clear_cache()
        with pytest.raises(AppError) as exc_info:
            complete(
                "parse",
                case_id=real_case_id,
                system="System prompt",
                user="User prompt",
                schema={"type": "object"},
            )

        assert exc_info.value.code == "LLM_UNAVAILABLE_LOCAL"
        assert exc_info.value.status_code == 503
        assert "Local LLM service is unavailable" in exc_info.value.message

    # Crucial assertion: Gemini was NEVER invoked during error/fallback in real mode
    assert mock_gemini.call_count == 0, "Security Invariant Violated: Gemini was invoked during real-mode failure!"

    # Audit log verification: failure recorded with route_reason=real_local_only
    with engine.connect() as conn:
        failed_call = conn.execute(
            text("SELECT provider, route_reason, status, error FROM llm_calls WHERE case_id = :cid ORDER BY created_at DESC LIMIT 1"),
            {"cid": real_case_id},
        ).fetchone()
        assert failed_call is not None
        assert failed_call[0] == "ollama"
        assert failed_call[1] == "real_local_only"
        assert failed_call[2] == "error"
        assert "connect to Ollama" in failed_call[3]


def test_tb9_3_demo_routing_and_fallback(temp_db):
    """
    TB9.3: Demo case routing & fallback:
    1. Demo case calls Gemini first with route_reason='demo_allowed'.
    2. On Gemini transient failure, falls back to Ollama with route_reason='fallback_after_error'.
    """
    engine = temp_db["engine"]
    demo_case_id = temp_db["demo_case_id"]
    settings.GEMINI_API_KEY = "AIzaSy_fake_test_gemini_key_12345"
    settings.LLM_PROVIDER_MODE = "auto"

    # Part A: Gemini succeeds
    mock_gemini_success = MagicMock(name="call_gemini", return_value=('{"attributes":{"jaw_shape":{"value":"square","source":"stated"}}}', 40, 25, 30))
    mock_ollama_spy = MagicMock(name="call_ollama")

    with patch("backend.app.llm.router.call_gemini", mock_gemini_success), \
         patch("backend.app.llm.router.call_ollama", mock_ollama_spy):

        clear_cache()
        res = complete(
            "parse",
            case_id=demo_case_id,
            system="System prompt",
            user="Demo prompt A",
            schema={"type": "object"},
        )
        assert res.provider == "gemini"
        assert res.route_reason == "demo_allowed"
        assert mock_gemini_success.call_count == 1
        assert mock_ollama_spy.call_count == 0

    # Part B: Gemini fails with transient error, falls back to Ollama
    mock_gemini_fail = MagicMock(name="call_gemini", side_effect=Exception("ResourceExhausted: 429 Rate limit exceeded"))
    mock_ollama_success = MagicMock(name="call_ollama", return_value=('{"attributes":{"jaw_shape":{"value":"square","source":"stated"}}}', 45, 20, 50))

    with patch("backend.app.llm.router.call_gemini", mock_gemini_fail), \
         patch("backend.app.llm.router.call_ollama", mock_ollama_success):

        clear_cache()
        res_fb = complete(
            "parse",
            case_id=demo_case_id,
            system="System prompt",
            user="Demo prompt B",
            schema={"type": "object"},
        )
        assert res_fb.provider == "ollama"
        assert res_fb.route_reason == "fallback_after_error"
        assert mock_gemini_fail.call_count == 1
        assert mock_ollama_success.call_count == 1

    # Check audit log in DB
    with engine.connect() as conn:
        calls = conn.execute(
            text("SELECT provider, route_reason, status FROM llm_calls WHERE case_id = :cid ORDER BY created_at ASC"),
            {"cid": demo_case_id},
        ).fetchall()
        # 1: gemini success
        assert calls[0][0] == "gemini"
        assert calls[0][1] == "demo_allowed"
        assert calls[0][2] == "ok"
        # 2: gemini failed
        assert calls[1][0] == "gemini"
        assert calls[1][1] == "demo_allowed"
        assert calls[1][2] == "error"
        # 3: ollama fallback
        assert calls[2][0] == "ollama"
        assert calls[2][1] == "fallback_after_error"
        assert calls[2][2] == "ok"


def test_tb9_4_provider_parity_and_guards(temp_db):
    """
    TB9.4: Provider parity and Responsible AI guards:
    Outputs from both Gemini and Ollama go through identical schema validation
    and Responsible AI guards. Unsupported inferences (unstated skin_tone, appearance_group)
    are stripped, valid attributes preserved, and outcomes are completely identical.
    """
    gemini_raw_output = {
        "attributes": {
            "face_shape": {"value": "oval", "source": "stated"},
            "hair_style": {"value": "curly", "source": "stated"},
            "skin_tone": {"value": "fair", "source": "inferred"},  # Unstated, must be dropped
            "appearance_group": {"value": "south_asian", "source": "inferred"},  # Unstated, must be dropped
            "eye_color": {"value": "laser_red", "source": "stated"},  # Invalid enum value
        },
        "unmapped_notes": ["scar on left cheek"],
    }

    ollama_raw_output = {
        "attributes": {
            "face_shape": {"value": "oval", "source": "stated"},
            "hair_style": {"value": "curly", "source": "stated"},
            "skin_tone": {"value": "fair", "source": "inferred"},  # Unstated, must be dropped
            "appearance_group": {"value": "south_asian", "source": "inferred"},  # Unstated, must be dropped
            "eye_color": {"value": "laser_red", "source": "stated"},  # Invalid enum value
        },
        "unmapped_notes": ["scar on left cheek"],
    }

    statement = "The suspect had an oval face with black curly hair and a visible scar on his left cheek."

    guarded_gemini, dropped_gemini = validate_and_guard_parse_delta(gemini_raw_output, statement)
    guarded_ollama, dropped_ollama = validate_and_guard_parse_delta(ollama_raw_output, statement)

    # 1. Parity: Guarded outputs must match 100%
    assert guarded_gemini == guarded_ollama

    # 2. Responsible AI: Inferred skin tone and appearance group dropped
    gemini_attrs = guarded_gemini["attributes"]
    assert "face_shape" in gemini_attrs
    assert gemini_attrs["face_shape"]["value"] == "oval"
    assert gemini_attrs["hair_style"]["value"] == "curly"

    assert "skin_tone" not in gemini_attrs
    assert "appearance_group" not in gemini_attrs
    assert "eye_color" not in gemini_attrs

    # 3. Check dropped reasons
    dropped_keys = [d["key"] for d in dropped_gemini]
    assert "skin_tone" in dropped_keys
    assert "appearance_group" in dropped_keys
    assert "eye_color" in dropped_keys

    # 4. Parity in dropped items
    assert [d["key"] for d in dropped_gemini] == [d["key"] for d in dropped_ollama]

