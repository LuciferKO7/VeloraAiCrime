import json
import os
import tempfile
import uuid
from pathlib import Path

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
from backend.app.services.eval_service import (  # noqa: E402
    compute_attribute_metrics,
    evaluate_probe_set,
    load_probe_set,
)

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
    roles = ["admin", "supervisor", "investigator", "artist", "auditor"]
    users = {}
    for r in roles:
        uid = str(uuid.uuid4())
        pwd = f"pass_{r}_123"
        ph = hash_password(pwd)
        con.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, failed_logins, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 0, ?)
            """,
            (uid, r, f"{r.capitalize()} User", r, ph, now),
        )
        users[r] = {"id": uid, "username": r, "role": r}

    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"timeout": 60})
    set_engine(engine)

    yield {
        "engine": engine,
        "users": users,
        "path": db_path,
    }

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


def _token(users: dict, role: str) -> str:
    user = users[role]
    return create_access_token(sub=user["id"], role=user["role"])


# ==============================================================================
# TB10.1: List glossary terms with status filtering
# ==============================================================================
def test_tb10_1_list_glossary_status_filter(temp_db, client):
    users = temp_db["users"]
    engine = temp_db["engine"]
    inv_tok = _token(users, "investigator")
    admin_id = users["admin"]["id"]
    now = "2026-10-28T12:00:00.000Z"

    # Seed pending, approved, and rejected terms
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO glossary_terms (id, language, term, maps_to_json, status, suggested_at)
                VALUES ('g1', 'ta', 'வட்ட முகம்', '{"attribute":"face_shape","value":"round"}', 'pending', :now)
                """
            ),
            {"now": now},
        )
        conn.execute(
            text(
                """
                INSERT INTO glossary_terms (id, language, term, maps_to_json, status, suggested_at, reviewed_by, reviewed_at)
                VALUES ('g2', 'hi', 'गोल चेहरा', '{"attribute":"face_shape","value":"round"}', 'approved', :now, :admin, :now)
                """
            ),
            {"now": now, "admin": admin_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO glossary_terms (id, language, term, maps_to_json, status, suggested_at, reviewed_by, reviewed_at)
                VALUES ('g3', 'en', 'laser eyes', '{"attribute":"face_shape","value":"oval"}', 'rejected', :now, :admin, :now)
                """
            ),
            {"now": now, "admin": admin_id},
        )

    # 1. Unauthenticated -> 401
    resp_unauth = client.get("/api/v1/glossary")
    assert resp_unauth.status_code == 401

    # 2. List all without status
    resp_all = client.get("/api/v1/glossary", headers={"Authorization": f"Bearer {inv_tok}"})
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert len(data_all) == 3
    assert all("maps_to" in d for d in data_all)

    # 3. Filter by pending
    resp_p = client.get("/api/v1/glossary?status=pending", headers={"Authorization": f"Bearer {inv_tok}"})
    assert resp_p.status_code == 200
    data_p = resp_p.json()
    assert len(data_p) == 1
    assert data_p[0]["id"] == "g1"
    assert data_p[0]["status"] == "pending"

    # 4. Filter by approved
    resp_a = client.get("/api/v1/glossary?status=approved", headers={"Authorization": f"Bearer {inv_tok}"})
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert len(data_a) == 1
    assert data_a[0]["id"] == "g2"
    assert data_a[0]["status"] == "approved"

    # 5. Invalid status filter -> 422
    resp_inv = client.get("/api/v1/glossary?status=invalid_status", headers={"Authorization": f"Bearer {inv_tok}"})
    assert resp_inv.status_code == 422


# ==============================================================================
# TB10.2: Suggest glossary term & audit
# ==============================================================================
def test_tb10_2_suggest_glossary_term(temp_db, client):
    users = temp_db["users"]
    engine = temp_db["engine"]
    inv_tok = _token(users, "investigator")

    payload = {
        "language": "ta",
        "term": "கூர்மையான தாடை",
        "maps_to": {
            "attribute": "jaw_shape",
            "value": "pointed",
        },
        "suggested_by_llm_call_id": "call-12345",
    }

    res = client.post(
        "/api/v1/glossary/suggest",
        json=payload,
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["term"] == "கூர்மையான தாடை"
    assert data["language"] == "ta"
    assert data["status"] == "pending"
    assert data["maps_to"] == {"attribute": "jaw_shape", "value": "pointed"}
    assert data["suggested_by_llm_call_id"] == "call-12345"
    created_id = data["id"]

    # Verify database persistence
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, term, status, maps_to_json FROM glossary_terms WHERE id = :id"),
            {"id": created_id},
        ).mappings().fetchone()
        assert row is not None
        assert row["status"] == "pending"
        parsed = json.loads(row["maps_to_json"])
        assert parsed["attribute"] == "jaw_shape"
        assert parsed["value"] == "pointed"


# ==============================================================================
# TB10.3: Suggest glossary validation & duplicate rejection
# ==============================================================================
def test_tb10_3_suggest_glossary_validation_and_conflict(temp_db, client):
    users = temp_db["users"]
    inv_tok = _token(users, "investigator")

    # 1. Invalid attribute
    res_bad_attr = client.post(
        "/api/v1/glossary/suggest",
        json={
            "language": "en",
            "term": "laser eyes",
            "maps_to": {"attribute": "superpower", "value": "laser"},
        },
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_bad_attr.status_code == 422
    assert res_bad_attr.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Invalid enum value for valid attribute
    res_bad_val = client.post(
        "/api/v1/glossary/suggest",
        json={
            "language": "en",
            "term": "triangle jaw",
            "maps_to": {"attribute": "jaw_shape", "value": "triangular_extra"},
        },
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_bad_val.status_code == 422
    assert res_bad_val.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Successful creation
    valid_payload = {
        "language": "hi",
        "term": "चौकोर जबड़ा",
        "maps_to": {"attribute": "jaw_shape", "value": "square"},
    }
    res_ok = client.post(
        "/api/v1/glossary/suggest",
        json=valid_payload,
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_ok.status_code == 201

    # 4. Duplicate (language, term) conflict -> 409 CONFLICT_VERSION
    res_dup = client.post(
        "/api/v1/glossary/suggest",
        json=valid_payload,
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_dup.status_code == 409
    assert res_dup.json()["error"]["code"] == "CONFLICT_VERSION"


# ==============================================================================
# TB10.4: Review glossary term (approve / reject) & RBAC
# ==============================================================================
def test_tb10_4_review_glossary_term(temp_db, client):
    users = temp_db["users"]
    engine = temp_db["engine"]
    inv_tok = _token(users, "investigator")
    sup_tok = _token(users, "supervisor")
    admin_tok = _token(users, "admin")
    now = "2026-10-28T12:00:00.000Z"

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO glossary_terms (id, language, term, maps_to_json, status, suggested_at)
                VALUES ('term-rev-1', 'en', 'hawk nose', '{"attribute":"nose_tip","value":"pointed"}', 'pending', :now),
                       ('term-rev-2', 'en', 'button nose', '{"attribute":"nose_tip","value":"upturned"}', 'pending', :now)
                """
            ),
            {"now": now},
        )

    # 1. Investigator role forbidden from review -> 403
    res_inv = client.post(
        "/api/v1/glossary/term-rev-1/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_inv.status_code == 403

    # 2. Supervisor approves -> 200 OK
    res_app = client.post(
        "/api/v1/glossary/term-rev-1/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert res_app.status_code == 200
    data_app = res_app.json()
    assert data_app["status"] == "approved"
    assert data_app["reviewed_by"] == users["supervisor"]["id"]
    assert data_app["reviewed_at"] is not None

    # Check DB and audit log
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, reviewed_by FROM glossary_terms WHERE id = 'term-rev-1'")).fetchone()
        assert row[0] == "approved"
        assert row[1] == users["supervisor"]["id"]

        audit = conn.execute(
            text("SELECT action, user_id FROM audit_log WHERE action = 'glossary.review' AND resource_id = 'term-rev-1'")
        ).fetchone()
        assert audit is not None
        assert audit[1] == users["supervisor"]["id"]

    # 3. Attempting to review already approved term -> 422
    res_repeat = client.post(
        "/api/v1/glossary/term-rev-1/review",
        json={"action": "reject"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert res_repeat.status_code == 422

    # 4. Admin rejects pending term -> 200 OK
    res_rej = client.post(
        "/api/v1/glossary/term-rev-2/review",
        json={"action": "reject"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "rejected"

    # 5. Non-existent term ID -> 404
    res_404 = client.post(
        "/api/v1/glossary/non-existent-id/review",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert res_404.status_code == 404

    # 6. Invalid review action -> 422
    res_bad_action = client.post(
        "/api/v1/glossary/term-rev-2/review",
        json={"action": "ignore"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert res_bad_action.status_code == 422


# ==============================================================================
# TB10.5: Model registry listing & RBAC
# ==============================================================================
def test_tb10_5_model_registry_list(temp_db, client):
    users = temp_db["users"]
    engine = temp_db["engine"]
    admin_tok = _token(users, "admin")
    sup_tok = _token(users, "supervisor")
    inv_tok = _token(users, "investigator")
    now = "2026-10-28T12:00:00.000Z"

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_registry (id, name, role, version, metrics_json, is_active, registered_at)
                VALUES ('m1', 'qwen2.5-parser', 'llm_parser', '1.0.0', '{"f1": 0.88}', 1, :now),
                       ('m2', 'indictrans2-ta', 'translator', '1.0.0', '{"bleu": 34.2}', 1, :now)
                """
            ),
            {"now": now},
        )

    # 1. Investigator forbidden -> 403
    res_inv = client.get("/api/v1/admin/models", headers={"Authorization": f"Bearer {inv_tok}"})
    assert res_inv.status_code == 403

    # 2. Supervisor allowed -> 200
    res_sup = client.get("/api/v1/admin/models", headers={"Authorization": f"Bearer {sup_tok}"})
    assert res_sup.status_code == 200

    # 3. Admin allowed -> 200
    res_admin = client.get("/api/v1/admin/models", headers={"Authorization": f"Bearer {admin_tok}"})
    assert res_admin.status_code == 200
    models = res_admin.json()
    assert len(models) == 2
    assert models[0]["name"] in ("qwen2.5-parser", "indictrans2-ta")
    assert isinstance(models[0]["metrics"], dict)


# ==============================================================================
# TB10.6: Create eval run & RBAC / validation
# ==============================================================================
def test_tb10_6_create_eval_run(temp_db, client):
    users = temp_db["users"]
    engine = temp_db["engine"]
    admin_tok = _token(users, "admin")
    inv_tok = _token(users, "investigator")

    # 1. Non-admin forbidden -> 403
    res_inv = client.post(
        "/api/v1/admin/eval-runs",
        json={"kind": "parser", "metrics": {"f1": 0.85}},
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_inv.status_code == 403

    # 2. Invalid eval run kind -> 422
    res_bad_kind = client.post(
        "/api/v1/admin/eval-runs",
        json={"kind": "unknown_eval_type", "metrics": {"f1": 0.85}},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert res_bad_kind.status_code == 422
    assert res_bad_kind.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Successful eval run creation
    payload = {
        "kind": "parser",
        "config": {"model": "qwen2.5:3b-instruct", "samples": 15},
        "metrics": {"precision": 0.88, "recall": 0.85, "f1": 0.8647},
    }
    res_ok = client.post(
        "/api/v1/admin/eval-runs",
        json=payload,
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert res_ok.status_code == 201
    data = res_ok.json()
    assert data["kind"] == "parser"
    assert data["config"]["model"] == "qwen2.5:3b-instruct"
    assert data["metrics"]["f1"] == 0.8647
    run_id = data["id"]

    # Verify DB & audit log
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, kind, metrics_json FROM eval_runs WHERE id = :id"), {"id": run_id}).mappings().fetchone()
        assert row is not None
        assert row["kind"] == "parser"

        audit = conn.execute(
            text("SELECT action, user_id FROM audit_log WHERE action = 'admin.eval_run' AND resource_id = :id"),
            {"id": run_id},
        ).fetchone()
        assert audit is not None
        assert audit[1] == users["admin"]["id"]


# ==============================================================================
# TB10.7: List & fetch eval runs
# ==============================================================================
def test_tb10_7_get_and_list_eval_runs(temp_db, client):
    users = temp_db["users"]
    engine = temp_db["engine"]
    auditor_tok = _token(users, "auditor")
    admin_id = users["admin"]["id"]
    now = "2026-10-28T12:00:00.000Z"

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO eval_runs (id, kind, config_json, metrics_json, created_by, created_at)
                VALUES ('run-p1', 'parser', :cfg_p, :met_p, :admin, :now),
                       ('run-v1', 'verifier', :cfg_v, :met_v, :admin, :now)
                """
            ),
            {
                "cfg_p": json.dumps({"samples": 15}),
                "met_p": json.dumps({"f1": 0.85}),
                "cfg_v": json.dumps({"pairs": 50}),
                "met_v": json.dumps({"accuracy": 0.92}),
                "admin": admin_id,
                "now": now,
            },
        )

    # 1. List all runs (auditor allowed)
    res_all = client.get("/api/v1/admin/eval-runs", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert len(data_all) == 2

    # 2. Filter by kind
    res_parser = client.get("/api/v1/admin/eval-runs?kind=parser", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_parser.status_code == 200
    data_parser = res_parser.json()
    assert len(data_parser) == 1
    assert data_parser[0]["id"] == "run-p1"
    assert data_parser[0]["metrics"]["f1"] == 0.85

    # 3. Get single run by ID
    res_single = client.get("/api/v1/admin/eval-runs/run-v1", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_single.status_code == 200
    data_single = res_single.json()
    assert data_single["id"] == "run-v1"
    assert data_single["metrics"]["accuracy"] == 0.92

    # 4. Get non-existent run -> 404
    res_404 = client.get("/api/v1/admin/eval-runs/non-existent-run", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_404.status_code == 404


# ==============================================================================
# TB10.8: Parser evaluation on probe set fixture
# ==============================================================================
def test_tb10_8_parser_eval_service():
    probe_path = ROOT / "backend" / "tests" / "fixtures" / "llm_probe_set.jsonl"
    assert probe_path.exists(), "Probe set fixture missing"

    # 1. Test load_probe_set
    records = load_probe_set(probe_path)
    assert len(records) >= 15
    assert all("statement" in r and "expected_attributes" in r for r in records)

    # 2. Perfect deterministic parser -> F1 = 1.0
    def perfect_parser(statement: str, language: str) -> dict:
        for r in records:
            if r["statement"] == statement:
                return r["expected_attributes"]
        return {}

    eval_perfect = evaluate_probe_set(probe_path, perfect_parser)
    assert eval_perfect["total_samples"] == len(records)
    assert eval_perfect["overall"]["precision"] == 1.0
    assert eval_perfect["overall"]["recall"] == 1.0
    assert eval_perfect["overall"]["f1"] == 1.0
    assert "en" in eval_perfect["by_language"]
    assert "ta" in eval_perfect["by_language"]

    # 3. Zero-prediction parser -> F1 = 0.0
    def empty_parser(statement: str, language: str) -> dict:
        return {}

    eval_empty = evaluate_probe_set(probe_path, empty_parser)
    assert eval_empty["overall"]["f1"] == 0.0
    assert eval_empty["overall"]["tp"] == 0

    # 4. Direct metric calculation test
    preds = [{"face_shape": "oval", "age_band": "adult"}]
    gts = [{"face_shape": "oval", "age_band": "young_adult"}]
    metrics = compute_attribute_metrics(preds, gts)
    assert metrics["overall"]["tp"] == 1  # face_shape matched
    assert metrics["overall"]["fp"] == 1  # age_band: adult predicted but not expected
    assert metrics["overall"]["fn"] == 1  # age_band: young_adult expected but not predicted
    assert metrics["overall"]["precision"] == 0.5
    assert metrics["overall"]["recall"] == 0.5
    assert metrics["overall"]["f1"] == 0.5

    # 5. Error handling: missing file
    with pytest.raises(FileNotFoundError):
        load_probe_set(ROOT / "non_existent_probe_file.jsonl")

    # 6. Error handling: malformed jsonl
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".jsonl") as f:
        f.write('{"id": 1, "statement": "hello"}\n')  # missing language and expected_attributes
        temp_name = f.name

    try:
        with pytest.raises(ValueError) as exc:
            load_probe_set(temp_name)
        assert "Missing required field" in str(exc.value)
    finally:
        os.unlink(temp_name)
