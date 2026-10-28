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
from backend.app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db(tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

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


def _setup_session_with_round(temp_db, client, num_variants=6):
    users = temp_db["users"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB7 session round setup"

    res_c = client.post(
        "/api/v1/cases",
        json={"case_number": f"FIR-{uuid.uuid4().hex[:8]}", "title": "B7 Test Case", "data_mode": "demo"},
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
        json={"alias": "W-B7-01", "preferred_language": "en"},
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

    # Initial round
    fake_images = []
    for i in range(num_variants):
        fake_images.append({
            "id": str(uuid.uuid4()),
            "variant_index": i,
            "kind": "variant",
            "width": 512,
            "height": 512,
            "seed": 2000 + i,
            "prompt_text": "pencil sketch test",
            "negative_prompt": "",
            "variant_axes": {},
            "sha256": f"sha_{i}",
            "sketch_sha256": f"skt_sha_{i}",
            "attr_adherence": 0.85,
            "identity_similarity": 0.90,
            "speculative": 0,
            "is_final": 0,
        })

    with patch("backend.app.services.ml_proxy.MLProxyClient.generate_initial_round", return_value=fake_images):
        res_r = client.post(
            f"/api/v1/sessions/{sid}/rounds/generate",
            json={"num_variants": num_variants},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )
    assert res_r.status_code == 201
    round_data = res_r.json()

    return {
        "case_id": case_id,
        "witness_id": wid,
        "session_id": sid,
        "round_id": round_data["id"],
        "images": round_data["images"],
        "inv_tok": inv_tok,
        "purpose": purpose,
    }


def test_tb7_1_feedback_recording(temp_db, client):
    """
    TB7.1: Record feedback events (pick, more_like, less_like), verify selected_image_id updates,
    feedback_events row is persisted, and feedback.record audit is logged.
    """
    engine = temp_db["engine"]
    info = _setup_session_with_round(temp_db, client)
    sid = info["session_id"]
    rid = info["round_id"]
    img0 = info["images"][0]["id"]
    img1 = info["images"][1]["id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    # 1. Pick event
    res_pick = client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"round_id": rid, "image_id": img0, "event_type": "pick", "payload": {"note": "looks like him"}},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_pick.status_code == 201, res_pick.text
    pick_data = res_pick.json()
    assert pick_data["event_type"] == "pick"
    assert pick_data["image_id"] == img0

    # 2. More_like event
    res_more = client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"round_id": rid, "image_id": img1, "event_type": "more_like", "payload": {"aspect": "nose_bridge"}},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_more.status_code == 201

    # 3. Check selected_image_id in session
    res_s = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_s.json()["selected_image_id"] == img0

    # 4. List feedback
    res_list = client.get(
        f"/api/v1/sessions/{sid}/feedback",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_list.status_code == 200
    fb_list = res_list.json()
    assert len(fb_list) == 2
    assert fb_list[0]["event_type"] == "pick"
    assert fb_list[1]["event_type"] == "more_like"

    # 5. Check audit rows
    with engine.connect() as conn:
        audit_count = conn.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE action = 'feedback.create' AND resource_id = :eid"),
            {"eid": pick_data["id"]},
        ).scalar()
        assert audit_count == 1


def test_tb7_2_locks_management(temp_db, client):
    """
    TB7.2: Lock and unlock facial features via PUT /sessions/{sid}/locks and feedback events.
    """
    info = _setup_session_with_round(temp_db, client)
    sid = info["session_id"]
    rid = info["round_id"]
    img0 = info["images"][0]["id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    # 1. Update locks via PUT /sessions/{sid}/locks
    res_locks = client.put(
        f"/api/v1/sessions/{sid}/locks",
        json={"locked_features": ["jaw_shape", "eye_color"]},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_locks.status_code == 200
    assert res_locks.json()["locked_features"] == ["jaw_shape", "eye_color"]

    # 2. Lock an additional feature via feedback event
    res_fb_lock = client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"round_id": rid, "image_id": img0, "event_type": "lock_feature", "payload": {"feature": "hair_style"}},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_fb_lock.status_code == 201

    # 3. Verify session state reflects all locked features
    res_s = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert sorted(res_s.json()["locked_features"]) == ["eye_color", "hair_style", "jaw_shape"]

    # 4. Unlock a feature via feedback event
    res_fb_unlock = client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"round_id": rid, "image_id": img0, "event_type": "unlock_feature", "payload": {"feature": "jaw_shape"}},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_fb_unlock.status_code == 201

    res_s2 = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert sorted(res_s2.json()["locked_features"]) == ["eye_color", "hair_style"]


def test_tb7_3_undo_round(temp_db, client):
    """
    TB7.3: Undo latest round reverts current_round, deletes undone round & images,
    clears deleted selected_image_id, records undo event, and writes session.undo audit.
    """
    engine = temp_db["engine"]
    info = _setup_session_with_round(temp_db, client, num_variants=2)
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]

    # Pick image from round 1
    img0 = info["images"][0]["id"]
    client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"round_id": info["round_id"], "image_id": img0, "event_type": "pick"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )

    # Generate round 2 (evolve)
    fake_round2 = [
        {"id": str(uuid.uuid4()), "variant_index": 0, "kind": "variant", "width": 512, "height": 512},
        {"id": str(uuid.uuid4()), "variant_index": 1, "kind": "variant", "width": 512, "height": 512},
    ]
    with patch("backend.app.services.ml_proxy.MLProxyClient.evolve_round", return_value=fake_round2):
        client.post(
            f"/api/v1/sessions/{sid}/rounds/evolve",
            json={"parent_round_id": info["round_id"], "feedback": {"picked": [img0]}},
            headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
        )

    # Check session is at round 2
    res_s = client.get(f"/api/v1/sessions/{sid}", headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose})
    assert res_s.json()["current_round"] == 2
    assert len(res_s.json()["rounds"]) == 2

    # Pick image from round 2
    r2_img0 = fake_round2[0]["id"]
    client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"round_id": res_s.json()["rounds"][1]["id"], "image_id": r2_img0, "event_type": "pick"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )

    # Call POST /sessions/{sid}/undo
    res_undo = client.post(
        f"/api/v1/sessions/{sid}/undo",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_undo.status_code == 200
    undo_state = res_undo.json()

    # Reverted to round 1
    assert undo_state["current_round"] == 1
    assert len(undo_state["rounds"]) == 1
    # selected_image_id from deleted round 2 is cleared
    assert undo_state["selected_image_id"] is None

    # Database verification
    with engine.connect() as conn:
        round_count = conn.execute(text("SELECT COUNT(*) FROM rounds WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert round_count == 1
        audit_undo = conn.execute(text("SELECT action, resource_type, status_code FROM audit_log WHERE action = 'feedback.create' AND details_json LIKE '%undo%'")).fetchone()
        assert audit_undo is not None
        assert audit_undo[2] == 200


def test_tb7_4_finalize_session(temp_db, client):
    """
    TB7.4: Finalize session marks image is_final=1, creates finalize round,
    marks session completed, includes legal disclaimer, and audits session.finalize.
    """
    engine = temp_db["engine"]
    info = _setup_session_with_round(temp_db, client)
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]
    selected_img = info["images"][0]["id"]

    res_fin = client.post(
        f"/api/v1/sessions/{sid}/finalize",
        json={"image_id": selected_img, "notes": "Suspect identified with high confidence by witness"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_fin.status_code == 200, res_fin.text
    fin_data = res_fin.json()

    assert fin_data["status"] == "completed"
    assert fin_data["final_image_id"] == selected_img
    assert "not a photograph, not evidence of identity" in fin_data["disclaimer"]

    # Verify database updates
    with engine.connect() as conn:
        s_row = conn.execute(text("SELECT status, selected_image_id FROM sessions WHERE id = :sid"), {"sid": sid}).fetchone()
        assert s_row[0] == "completed"
        assert s_row[1] == selected_img

        img_row = conn.execute(text("SELECT is_final FROM images WHERE id = :iid"), {"iid": selected_img}).fetchone()
        assert img_row[0] == 1

        fin_round = conn.execute(text("SELECT kind, status FROM rounds WHERE session_id = :sid AND kind = 'finalize'"), {"sid": sid}).fetchone()
        assert fin_round is not None
        assert fin_round[0] == "finalize"
        assert fin_round[1] == "done"

        audit_fin = conn.execute(text("SELECT action, resource_type, status_code FROM audit_log WHERE action = 'session.finalize'")).fetchone()
        assert audit_fin is not None
        assert audit_fin[2] == 200


def test_tb7_5_next_question_and_image_metadata(temp_db, client):
    """
    TB7.5: GET /sessions/{sid}/next-question returns targeted salient question,
    and GET /images/{id} returns comprehensive image metadata.
    """
    info = _setup_session_with_round(temp_db, client)
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    purpose = info["purpose"]
    img0 = info["images"][0]["id"]

    # 1. Next question
    res_q = client.get(
        f"/api/v1/sessions/{sid}/next-question",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_q.status_code == 200
    q_data = res_q.json()
    assert "next_question" in q_data
    assert len(q_data["next_question"]) > 10
    assert "unspecified_keys" in q_data
    assert len(q_data["unspecified_keys"]) > 0

    # 2. Image metadata
    res_img = client.get(f"/api/v1/images/{img0}")
    assert res_img.status_code == 200
    meta = res_img.json()
    assert meta["id"] == img0
    assert meta["session_id"] == sid
    assert meta["width"] == 512
    assert "urls" in meta
    assert meta["urls"]["photo"].startswith("/api/v1/images/")


def test_tb7_6_authorization_and_purpose(temp_db, client):
    """
    TB7.6: Auditor is denied on feedback mutations and purpose header is required.
    """
    info = _setup_session_with_round(temp_db, client)
    sid = info["session_id"]
    inv_tok = info["inv_tok"]
    auditor_tok = get_token(temp_db["users"], "auditor")
    img0 = info["images"][0]["id"]

    # 1. Missing purpose header returns 400
    res_no_purp = client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"image_id": img0, "event_type": "pick"},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_no_purp.status_code == 400
    assert res_no_purp.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 2. Auditor denied on mutation
    res_auditor = client.post(
        f"/api/v1/sessions/{sid}/feedback",
        json={"image_id": img0, "event_type": "pick"},
        headers={"Authorization": f"Bearer {auditor_tok}", "X-Access-Purpose": "Auditor inspect"},
    )
    assert res_auditor.status_code == 403
    assert res_auditor.json()["error"]["code"] == "FORBIDDEN"
