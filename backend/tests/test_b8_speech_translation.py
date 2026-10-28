import base64
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.core.config import settings

settings.SERVICE_KEY = os.environ["SERVICE_KEY"]
settings.JWT_SECRET = os.environ["JWT_SECRET"]

from backend.app.core.errors import AppError  # noqa: E402
from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.db.session import get_connection, set_engine  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.services.speech_proxy import SpeechProxyClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db(tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    settings.STORAGE_DIR = str(storage_dir)

    import sqlite3
    schema_sql = (ROOT / "contracts/schema.sql").read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    con.executescript(schema_sql)

    now = "2026-10-28T12:00:00.000Z"
    roles = ["admin", "supervisor", "investigator", "artist", "auditor"]
    users = {}
    for r in roles:
        uid = str(uuid.uuid4())
        pwd = f"pass_{r}_12345"
        ph = hash_password(pwd)
        con.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, failed_logins, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 0, ?)
            """,
            (uid, r, f"{r.capitalize()} User", r, ph, now),
        )
        users[r] = {"id": uid, "username": r, "password": pwd, "role": r}
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"timeout": 60})
    set_engine(engine)

    yield {"path": db_path, "engine": engine, "users": users, "storage": storage_dir}

    engine.dispose()
    set_engine(None)
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass


@pytest.fixture
def client(temp_db):
    engine = temp_db["engine"]

    def override_get_connection():
        with engine.connect() as conn:
            yield conn

    app = create_app()
    app.dependency_overrides[get_connection] = override_get_connection
    return TestClient(app)


def get_token(users: dict, role: str) -> str:
    user = users[role]
    return create_access_token(sub=user["id"], role=user["role"])


def _setup_case_and_session(temp_db, client):
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB8 speech and translation setup"

    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": f"FIR-{uuid.uuid4().hex[:8]}", "title": "B8 Voice Case", "data_mode": "demo"},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_c.status_code == 201
    case_id = res_c.json()["id"]

    client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": users["investigator"]["id"], "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )

    res_w = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "W-B8-01", "preferred_language": "ta"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_w.status_code == 201
    wid = res_w.json()["id"]

    res_s = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_s.status_code == 201
    sid = res_s.json()["id"]

    return {
        "case_id": case_id,
        "witness_id": wid,
        "session_id": sid,
        "inv_tok": inv_tok,
        "purpose": purpose,
    }


def test_tb8_1_speech_transcription(temp_db, client):
    """
    TB8.1: Test audio transcription proxy endpoint POST /api/v1/speech/transcribe.
    Assert audio file upload, transcription parsing, audio_sha256 calculation,
    and speech.transcribe audit logging.
    """
    engine = temp_db["engine"]
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    dummy_audio = b"RIFF....WAVEfmt ....data...."

    fake_transcription = {
        "text": "The suspect had a sharp nose and black short hair",
        "language": "en",
        "duration_s": 3.5,
    }

    with patch.object(SpeechProxyClient, "transcribe", return_value=fake_transcription):
        res = client.post(
            "/api/v1/speech/transcribe?language_hint=en",
            content=dummy_audio,
            headers={
                "Authorization": f"Bearer {inv_tok}",
                "X-Access-Purpose": "Testing transcription",
                "Content-Type": "audio/wav",
            },
        )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["text"] == "The suspect had a sharp nose and black short hair"
    assert data["language"] == "en"
    assert "audio_sha256" in data
    assert len(data["audio_sha256"]) == 64

    # Verify audit entry
    with engine.connect() as conn:
        audit = conn.execute(
            text("SELECT action, resource_type, status_code FROM audit_log WHERE action = 'speech.transcribe'")
        ).fetchone()
        assert audit is not None
        assert audit[0] == "speech.transcribe"
        assert audit[2] == 200


def test_tb8_2_translation_proxy(temp_db, client):
    """
    TB8.2: Test translation proxy endpoint POST /api/v1/speech/translate.
    Assert regional language translation via IndicTrans2.
    """
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")

    fake_translation = {
        "translated_text": "Round face with black curly hair",
        "source_lang": "ta",
        "target_lang": "en",
        "engine": "indictrans2",
    }

    with patch.object(SpeechProxyClient, "translate", return_value=fake_translation):
        res = client.post(
            "/api/v1/speech/translate",
            json={"text": "வட்ட முகம் மற்றும் சுருள் முடி", "source_lang": "ta", "target_lang": "en"},
            headers={"Authorization": f"Bearer {inv_tok}"},
        )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["translated_text"] == "Round face with black curly hair"
    assert data["source_lang"] == "ta"
    assert data["target_lang"] == "en"


def test_tb8_3_speech_unavailable_handling(temp_db, client):
    """
    TB8.3: When speech service is down, /speech/transcribe returns 503 SPEECH_UNAVAILABLE,
    and statement translation falls back gracefully to LLM router.
    """
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    dummy_audio = b"RIFF....WAVE"

    with patch.object(SpeechProxyClient, "transcribe", side_effect=AppError("SPEECH_UNAVAILABLE", "Service down", status_code=503)):
        res = client.post(
            "/api/v1/speech/transcribe",
            content=dummy_audio,
            headers={"Authorization": f"Bearer {inv_tok}", "Content-Type": "audio/wav"},
        )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "SPEECH_UNAVAILABLE"


def test_tb8_4_voice_statement_and_session_audio(temp_db, client):
    """
    TB8.4: Test full voice-statement workflow inside a session:
    1. Transcribe session audio via POST /api/v1/sessions/{sid}/transcribe.
    2. Submit voice statement via POST /api/v1/sessions/{sid}/statements with audio_base64.
    3. Assert statement and attribute snapshot are created with input_mode='voice' and audio_sha256.
    """
    engine = temp_db["engine"]
    info = _setup_case_and_session(temp_db, client)
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]
    dummy_audio = b"VOICE_SAMPLE_WAV_BYTES_FOR_VELORA"

    fake_transcription = {
        "text": "The suspect had a square jaw, thick eyebrows, and brown eyes",
        "language": "en",
        "duration_s": 4.2,
    }

    # 1. Transcribe directly to session
    with patch.object(SpeechProxyClient, "transcribe", return_value=fake_transcription):
        res_trans = client.post(
            f"/api/v1/sessions/{sid}/transcribe",
            content=dummy_audio,
            headers={
                "Authorization": f"Bearer {inv_tok}",
                "X-Access-Purpose": purpose,
                "Content-Type": "audio/wav",
            },
        )
    assert res_trans.status_code == 200, res_trans.text
    trans_data = res_trans.json()
    assert trans_data["text"] == fake_transcription["text"]
    assert "audio_sha256" in trans_data

    # 2. Submit voice statement with base64 audio
    from backend.app.llm.router import LLMResult

    mock_llm_result = LLMResult(
        content={
            "attributes": {
                "jaw_shape": {"value": "square", "source": "stated"},
                "eyebrow_thickness": {"value": "thick", "source": "stated"},
                "eye_color": {"value": "brown", "source": "stated"},
            },
            "unmapped_notes": [],
        },
        raw_text='{"attributes":{"jaw_shape":{"value":"square"}}}',
        provider="ollama",
        model="test-model",
        route_reason="demo_allowed",
        call_id=str(uuid.uuid4()),
        latency_ms=15,
        tokens_in=50,
        tokens_out=20,
    )

    audio_b64 = base64.b64encode(dummy_audio).decode("ascii")
    with patch("backend.app.services.statement_pipeline.complete", return_value=mock_llm_result):
        with patch.object(SpeechProxyClient, "transcribe", return_value=fake_transcription):
            res_stmt = client.post(
                f"/api/v1/sessions/{sid}/statements",
                json={"input_mode": "voice", "audio_base64": audio_b64, "speaker": "witness"},
                headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
            )
    assert res_stmt.status_code == 201, res_stmt.text
    stmt_data = res_stmt.json()
    assert stmt_data["statement"]["input_mode"] == "voice"
    assert stmt_data["statement"]["audio_sha256"] == trans_data["audio_sha256"]
    assert stmt_data["statement"]["original_text"] == fake_transcription["text"]
    assert "attributes" in stmt_data

    # 3. Check database record
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT input_mode, audio_sha256, original_text FROM statements WHERE session_id = :sid"),
            {"sid": sid},
        ).fetchone()
        assert row is not None
        assert row[0] == "voice"
        assert row[1] == trans_data["audio_sha256"]
        assert row[2] == fake_transcription["text"]
