import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

# Set test environment variables before importing app
os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.core.config import settings

settings.SERVICE_KEY = os.environ["SERVICE_KEY"]
settings.JWT_SECRET = os.environ["JWT_SECRET"]

from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.db.session import get_connection, set_engine  # noqa: E402
from backend.app.llm.router import LLMResult  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.services.statement_pipeline import detect_language, translate_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

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

    yield {"path": db_path, "engine": engine, "users": users}

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


def test_language_detection():
    """Test Indic Unicode detection & English default."""
    assert detect_language("சந்தேக நபர் சுமார் 30 வயது") == "ta"
    assert detect_language("संदिग्ध व्यक्ति लगभग 30 वर्ष का था") == "hi"
    assert detect_language("संशयित व्यक्ती सुमारे 30 वर्षांची होती", preferred_hint="mr") == "mr"
    assert detect_language("সন্দেহভাজন ব্যক্তির বয়স প্রায় ৩০ বছর") == "bn"
    assert detect_language("నిందితుడు దాదాపు 30 సంవత్సరాల వయస్సు") == "te"
    assert detect_language("ಅನುಮಾನಾಸ್ಪದ ವ್ಯಕ್ತಿಯ ವಯಸ್ಸು ಸುಮಾರು 30 ವರ್ಷ") == "kn"
    assert detect_language("The suspect was an adult man with an oval face") == "en"


def test_statement_submission_and_snapshot_pipeline(temp_db, client):
    """
    TB5 Core: Submit statement in Tamil, verify language detection, translation fallback,
    parsing, guards, attribute snapshot versioning, and next question.
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB5 pipeline verification"

    # 1. Create case & grant investigator access
    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-2026-TB5-001", "title": "TB5 Statement Test", "data_mode": "demo"},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_c.status_code == 201, res_c.text
    case_id = res_c.json()["id"]

    client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": users["investigator"]["id"], "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )

    # 2. Create Tamil witness
    res_w = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "W-TAMIL-B5", "preferred_language": "ta"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_w.status_code == 201, res_w.text
    wid = res_w.json()["id"]

    # 3. Create session
    res_s = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_s.status_code == 201, res_s.text
    sid = res_s.json()["id"]

    # 4. Mock parsed LLM output
    mock_call_id = str(uuid.uuid4())
    mock_llm_result = LLMResult(
        content={
            "attributes": {
                "face_shape": {"value": "oval", "source": "stated"},
                "facial_hair_type": {"value": "mustache", "source": "stated"},
                "hair_style": {"value": "curly", "source": "stated"},
                "hair_length": {"value": "short", "source": "stated"},
            },
            "unmapped_notes": ["witness noted high cheekbones"],
        },
        raw_text=json.dumps({
            "attributes": {
                "face_shape": {"value": "oval", "source": "stated"},
                "facial_hair_type": {"value": "mustache", "source": "stated"},
            }
        }),
        provider="gemini",
        model="gemini-2.5-flash",
        route_reason="demo_allowed",
        latency_ms=120,
        tokens_in=50,
        tokens_out=40,
        call_id=mock_call_id,
    )

    stmt_payload = {
        "text": "The suspect was a young adult man with an oval face, thick mustache, and short curly hair.",
        "speaker": "witness",
        "input_mode": "text",
        "audio_sha256": "abcdef1234567890",
    }

    with patch("backend.app.services.statement_pipeline.complete", return_value=mock_llm_result):
        res_stmt = client.post(
            f"/api/v1/sessions/{sid}/statements",
            json=stmt_payload,
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res_stmt.status_code == 201, res_stmt.text
    stmt_data = res_stmt.json()

    # Check statement record
    statement = stmt_data["statement"]
    assert statement["original_lang"] == "en"
    assert statement["english_text"] == stmt_payload["text"]
    assert statement["audio_sha256"] == "abcdef1234567890"

    # Check attributes & assumptions
    attrs = stmt_data["attributes"]
    assert attrs["schema_version"] == "1.0"
    assert attrs["attributes"]["face_shape"]["value"] == "oval"
    assert "witness noted high cheekbones" in attrs["unmapped_notes"]

    assumptions = stmt_data["assumptions"]
    assert len(assumptions) > 0

    # Next question exists
    assert "next_question" in stmt_data
    assert len(stmt_data["next_question"]) > 10

    # Check database snapshot row
    with engine.connect() as conn:
        snap_row = conn.execute(
            text("SELECT version, change_source, derived_from_statement_id, llm_call_id FROM attribute_snapshots WHERE session_id = :sid"),
            {"sid": sid},
        ).fetchone()
        assert snap_row is not None
        assert snap_row[0] == 1
        assert snap_row[1] == "statement"
        assert snap_row[2] == statement["id"]
        assert snap_row[3] == mock_call_id

        # Audit log verified
        audit_row = conn.execute(
            text("SELECT action, resource_type, status_code FROM audit_log WHERE resource_id = :rid"),
            {"rid": statement["id"]},
        ).fetchone()
        assert audit_row is not None
        assert audit_row[0] == "statement.create"
        assert audit_row[2] == 201


def test_guard_rejection_of_unstated_appearance(temp_db, client):
    """
    TB5 Guard: Verify that if LLM returns an unstated appearance_group or skin_tone,
    guards drop them automatically.
    """
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB5 guard test"

    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-2026-TB5-003", "title": "Guard Test Case", "data_mode": "demo"},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    case_id = res_c.json()["id"]

    client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": users["investigator"]["id"], "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )

    res_w = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "W-GUARD-01", "preferred_language": "en"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    wid = res_w.json()["id"]

    res_s = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    sid = res_s.json()["id"]

    # LLM hallucinates appearance_group and skin_tone without words in text
    mock_llm_result = LLMResult(
        content={
            "attributes": {
                "face_shape": {"value": "oval", "source": "stated"},
                "appearance_group": {"value": "south_asian", "source": "stated"},
                "skin_tone": {"value": "wheatish", "source": "stated"},
            },
            "unmapped_notes": [],
        },
        raw_text="{}",
        provider="gemini",
        model="gemini-2.5-flash",
        route_reason="demo_allowed",
        latency_ms=100,
        tokens_in=50,
        tokens_out=40,
        call_id=str(uuid.uuid4()),
    )

    with patch("backend.app.services.statement_pipeline.complete", return_value=mock_llm_result):
        res = client.post(
            f"/api/v1/sessions/{sid}/statements",
            json={"text": "He had an oval face.", "speaker": "witness"},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res.status_code == 201, res.text
    res_data = res.json()
    attrs = res_data["attributes"]["attributes"]

    # Guards must drop unstated appearance_group and skin_tone
    assert "face_shape" in attrs
    assert "appearance_group" not in attrs
    assert "skin_tone" not in attrs


def test_translation_fallback():
    """
    TB5 Translation: Verify that when speech service fails, translation falls back to LLM router.
    """
    mock_trans_result = LLMResult(
        content="The suspect was tall with a round face.",
        raw_text="The suspect was tall with a round face.",
        provider="gemini",
        model="gemini-2.5-flash",
        route_reason="demo_allowed",
        latency_ms=150,
        tokens_in=30,
        tokens_out=25,
        call_id=str(uuid.uuid4()),
    )

    with patch("backend.app.services.statement_pipeline.complete", return_value=mock_trans_result):
        eng, engine = translate_text("சந்தேக நபர் உயரமாகவும் வட்ட முகத்துடனும் இருந்தார்.", "ta")
        assert eng == "The suspect was tall with a round face."
        assert engine == "gemini"


def test_manual_attributes_update(temp_db, client):
    """
    Test PUT /sessions/{sid}/attributes updates snapshot with change_source='user_edit'.
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB5 manual attributes update"

    # Setup case, grant, witness, session
    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-2026-TB5-002", "title": "TB5 Edit Test", "data_mode": "demo"},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    case_id = res_c.json()["id"]

    client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": users["investigator"]["id"], "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )

    res_w = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "W-EDIT-01", "preferred_language": "en"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    wid = res_w.json()["id"]

    res_s = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    sid = res_s.json()["id"]

    # Officer manually updates attributes
    update_payload = {
        "attributes": {
            "jaw_shape": "square",
            "eye_color": {"value": "dark_brown", "confidence": "sure"},
        },
        "unmapped_notes": ["scar on left cheek"],
    }
    res_put = client.put(
        f"/api/v1/sessions/{sid}/attributes",
        json=update_payload,
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_put.status_code == 200, res_put.text
    put_data = res_put.json()

    assert put_data["version"] == 1
    assert put_data["attributes"]["attributes"]["jaw_shape"]["value"] == "square"
    assert put_data["attributes"]["attributes"]["jaw_shape"]["source"] == "user_edit"
    assert put_data["attributes"]["attributes"]["eye_color"]["value"] == "dark_brown"
    assert "scar on left cheek" in put_data["attributes"]["unmapped_notes"]

    # Verify audit row
    with engine.connect() as conn:
        audit_row = conn.execute(
            text("SELECT action, resource_type, status_code FROM audit_log WHERE resource_id = :sid AND action = 'attributes.update'"),
            {"sid": sid},
        ).fetchone()
        assert audit_row is not None
        assert audit_row[0] == "attributes.update"
        assert audit_row[2] == 200


def test_real_case_local_only_routing(temp_db, client):
    """
    TB5 Real Case: Verify that when case data_mode is 'real',
    LLM routing exclusively uses local Ollama and never calls Gemini.
    """
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB5 real case privacy test"

    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-2026-REAL-B5", "title": "Real Case Privacy", "data_mode": "real"},
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
        json={"alias": "W-REAL-01", "preferred_language": "en"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    wid = res_w.json()["id"]

    res_s = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    sid = res_s.json()["id"]

    all_keys = [
        "sex_presentation", "age_band", "appearance_group", "face_shape", "skin_tone",
        "forehead", "cheeks", "jaw_shape", "jaw_width", "chin", "eye_shape", "eye_size",
        "eye_spacing", "eye_color", "eyebrow_thickness", "eyebrow_shape", "nose_bridge",
        "nose_length", "nose_tip", "nostrils", "lips_fullness", "mouth_width", "ears",
        "hair_length", "hair_style", "hair_color", "hairline", "facial_hair_type",
        "facial_hair_density", "facial_hair_length", "glasses", "headwear",
    ]
    raw_attrs = {k: None for k in all_keys}
    raw_attrs["face_shape"] = {"value": "round", "source": "stated"}

    mock_ollama_raw = json.dumps({
        "schema_version": "1.0",
        "attributes": raw_attrs,
        "marks": [],
        "unmapped_notes": [],
    })

    with patch("backend.app.llm.router.call_ollama", return_value=(mock_ollama_raw, 20, 15, 80)) as mock_ollama, \
         patch("backend.app.llm.router.call_gemini") as mock_gemini:
        res_stmt = client.post(
            f"/api/v1/sessions/{sid}/statements",
            json={"text": "He had a round face.", "speaker": "witness"},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
        assert res_stmt.status_code == 201, res_stmt.text
        assert mock_ollama.called
        assert not mock_gemini.called

