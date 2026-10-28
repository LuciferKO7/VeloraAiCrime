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
from backend.app.core.errors import AppError

settings.SERVICE_KEY = os.environ["SERVICE_KEY"]
settings.JWT_SECRET = os.environ["JWT_SECRET"]

from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.db.session import get_connection, set_engine  # noqa: E402
from backend.app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db(tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    # Use tmp_path for storage during tests
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    settings.STORAGE_DIR = str(storage_dir)

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


def _setup_session(temp_db, client, case_title="B6 Round Test Case"):
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB6 setup verification"

    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": f"FIR-{uuid.uuid4().hex[:8]}", "title": case_title, "data_mode": "demo"},
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
        json={"alias": "W-B6-01", "preferred_language": "en"},
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

    return {"case_id": case_id, "witness_id": wid, "session_id": sid, "inv_tok": inv_tok, "purpose": purpose}


def _fake_ml_generate_response(num_variants=6):
    images = []
    for i in range(num_variants):
        images.append({
            "id": str(uuid.uuid4()),
            "variant_index": i,
            "kind": "variant",
            "width": 512,
            "height": 512,
            "seed": 1000 + i,
            "prompt_text": "pencil sketch of adult male face",
            "negative_prompt": "blurry, low quality",
            "variant_axes": {"jaw_width": 0.5 + i * 0.1},
            "sha256": f"dummy_sha_{i}",
            "sketch_sha256": f"dummy_skt_sha_{i}",
            "attr_adherence": 0.85,
            "identity_similarity": 0.90,
            "speculative": 0,
            "is_final": 0,
            "model_versions": {"image_gen": "sd-1.5", "inpaint": "sd-inpaint"},
        })
    return images


def test_tb6_1_initial_round_generation(temp_db, client):
    """
    TB6.1: Initial round generation proxies to ML service, creates round row (kind='initial', round_no=1),
    creates 6 image variants, updates session, and audits round.generate.
    """
    engine = temp_db["engine"]
    info = _setup_session(temp_db, client, "TB6.1 Initial Generation")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    fake_images = _fake_ml_generate_response(6)

    with patch("backend.app.services.ml_proxy.MLProxyClient.generate_initial_round", return_value=fake_images):
        res = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 6, "seed": 42},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["session_id"] == sid
    assert data["round_no"] == 1
    assert data["kind"] == "initial"
    assert data["status"] == "done"
    assert len(data["images"]) == 6

    # Verify first image structure
    img0 = data["images"][0]
    assert img0["variant_index"] == 0
    assert img0["width"] == 512
    assert "urls" in img0
    assert img0["urls"]["photo"].startswith("/api/v1/images/")
    assert img0["urls"]["pencil"].startswith("/api/v1/images/")

    # Verify database persistence
    with engine.connect() as conn:
        r_row = conn.execute(text("SELECT round_no, kind, status FROM rounds WHERE session_id = :sid"), {"sid": sid}).fetchone()
        assert r_row is not None
        assert r_row[0] == 1
        assert r_row[1] == "initial"
        assert r_row[2] == "done"

        img_count = conn.execute(text("SELECT COUNT(*) FROM images WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert img_count == 6

        # Audit row
        audit_row = conn.execute(text("SELECT action, resource_type, status_code FROM audit_log WHERE resource_id = :rid"), {"rid": data["id"]}).fetchone()
        assert audit_row is not None
        assert audit_row[0] == "round.generate"
        assert audit_row[2] == 201


def test_tb6_2_session_state_reflects_round(temp_db, client):
    """
    TB6.2: GET /sessions/{sid} reflects the newly generated round and images in SessionState.
    """
    info = _setup_session(temp_db, client, "TB6.2 Session State")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    fake_images = _fake_ml_generate_response(6)
    with patch("backend.app.services.ml_proxy.MLProxyClient.generate_initial_round", return_value=fake_images):
        client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 6},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )

    # Fetch SessionState
    res_sess = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_sess.status_code == 200
    state = res_sess.json()
    assert state["current_round"] == 1
    assert len(state["rounds"]) == 1
    assert len(state["rounds"][0]["images"]) == 6

    # Fetch rounds list endpoint
    res_r_list = client.get(
        f"/api/v1/sessions/{sid}/rounds",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_r_list.status_code == 200
    rounds_list = res_r_list.json()
    assert len(rounds_list) == 1

    # Fetch single round endpoint
    rid = rounds_list[0]["id"]
    res_single = client.get(
        f"/api/v1/sessions/{sid}/rounds/{rid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_single.status_code == 200
    assert res_single.json()["id"] == rid


def test_tb6_3_image_file_serving(temp_db, client):
    """
    TB6.3: Image file serving route GET /api/v1/images/{id}/file serves photo and pencil PNGs.
    """
    info = _setup_session(temp_db, client, "TB6.3 Image File Serving")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    fake_images = _fake_ml_generate_response(1)
    with patch("backend.app.services.ml_proxy.MLProxyClient.generate_initial_round", return_value=fake_images):
        res_r = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 1},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    img_id = res_r.json()["images"][0]["id"]

    # Serve photo
    res_img = client.get(f"/api/v1/images/{img_id}/file?style=photo")
    assert res_img.status_code == 200
    assert res_img.headers["content-type"] == "image/png"
    assert len(res_img.content) > 0

    # Serve pencil
    res_skt = client.get(f"/api/v1/images/{img_id}/file?style=pencil")
    assert res_skt.status_code == 200
    assert res_skt.headers["content-type"] == "image/png"

    # Non-existent image returns 404
    res_404 = client.get(f"/api/v1/images/{uuid.uuid4()}/file")
    assert res_404.status_code == 404


def test_tb6_4_ml_service_unavailable(temp_db, client):
    """
    TB6.4: When ML service is down/unreachable, returns 503 ML_UNAVAILABLE and rolls back round creation.
    """
    engine = temp_db["engine"]
    info = _setup_session(temp_db, client, "TB6.4 ML Unavailable")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    with patch("backend.app.services.ml_proxy.MLProxyClient._send_request", side_effect=AppError("ML_UNAVAILABLE", "ML service down", 503)):
        res = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 6},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "ML_UNAVAILABLE"

    # Confirm no partial round exists
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM rounds WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert count == 0


def test_tb6_5_ml_service_busy(temp_db, client):
    """
    TB6.5: When ML service returns busy (429 or 503 ML_BUSY), returns 503 ML_BUSY.
    """
    info = _setup_session(temp_db, client, "TB6.5 ML Busy")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    with patch("backend.app.services.ml_proxy.MLProxyClient._send_request", side_effect=AppError("ML_BUSY", "ML GPU pipeline busy", 503)):
        res = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 6},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res.status_code in (429, 503)
    assert res.json()["error"]["code"] == "ML_BUSY"


def test_tb6_6_evolve_round(temp_db, client):
    """
    TB6.6: Evolve round generates round_no=2 with kind='evolve' and links parent feedback.
    """
    info = _setup_session(temp_db, client, "TB6.6 Evolve Round")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    # Initial round
    with patch("backend.app.services.ml_proxy.MLProxyClient.generate_initial_round", return_value=_fake_ml_generate_response(6)):
        r1_res = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 6},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    parent_rid = r1_res.json()["id"]
    picked_img = r1_res.json()["images"][0]["id"]

    # Evolve round
    with patch("backend.app.services.ml_proxy.MLProxyClient.evolve_round", return_value=_fake_ml_generate_response(6)):
        res_evolve = client.post(
            f"/api/v1/sessions/{sid}/rounds/evolve",
            json={
                "parent_round_id": parent_rid,
                "feedback": {"picked": [picked_img], "more_like": [], "less_like": []},
                "num_variants": 6,
            },
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res_evolve.status_code == 201, res_evolve.text
    r2_data = res_evolve.json()
    assert r2_data["round_no"] == 2
    assert r2_data["kind"] == "evolve"
    assert len(r2_data["images"]) == 6


def test_tb6_7_edit_round(temp_db, client):
    """
    TB6.7: Edit round modifies parent image with instruction text and records kind='edit'.
    """
    info = _setup_session(temp_db, client, "TB6.7 Edit Round")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    with patch("backend.app.services.ml_proxy.MLProxyClient.generate_initial_round", return_value=_fake_ml_generate_response(1)):
        r1_res = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": 1},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    parent_img = r1_res.json()["images"][0]["id"]

    edit_images = [{
        "id": str(uuid.uuid4()),
        "variant_index": 0,
        "kind": "edit",
        "parent_image_id": parent_img,
        "width": 512,
        "height": 512,
        "seed": 9999,
        "prompt_text": "pointed chin edit",
        "negative_prompt": "",
        "variant_axes": {},
        "sha256": "edit_sha_123",
        "sketch_sha256": "edit_skt_sha_123",
        "attr_adherence": 0.90,
        "identity_similarity": 0.88,
        "speculative": 0,
        "is_final": 0,
    }]

    with patch("backend.app.services.ml_proxy.MLProxyClient.edit_round", return_value=edit_images):
        res_edit = client.post(
            f"/api/v1/sessions/{sid}/rounds/edit",
            json={"parent_image_id": parent_img, "instruction_text": "make chin more pointed", "kind": "edit"},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res_edit.status_code == 201, res_edit.text
    edit_data = res_edit.json()
    assert edit_data["round_no"] == 2
    assert edit_data["kind"] == "edit"
    assert edit_data["images"][0]["parent_image_id"] == parent_img


def test_tb6_8_authorization_purpose_and_audit(temp_db, client):
    """
    TB6.8: Verify auditor denial (403 FORBIDDEN and access.denied), purpose header requirement,
    and audit log generation.
    """
    info = _setup_session(temp_db, client, "TB6.8 Auth & Audit")
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    auditor_tok = get_token(temp_db["users"], "auditor")

    # 1. Missing X-Access-Purpose returns 400 PURPOSE_REQUIRED
    res_no_purpose = client.post(
        f"/api/v1/sessions/{sid}/rounds/generate",
        json={"num_variants": 6},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_no_purpose.status_code == 400
    assert res_no_purpose.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 2. Auditor is denied
    res_auditor = client.post(
        f"/api/v1/sessions/{sid}/rounds/generate",
        json={"num_variants": 6},
        headers={"Authorization": f"Bearer {auditor_tok}", "X-Access-Purpose": "Auditor inspect"},
    )
    assert res_auditor.status_code == 403
    assert res_auditor.json()["error"]["code"] == "FORBIDDEN"
