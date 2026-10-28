import os
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"
os.environ["SEED_PASSWORD_ADMIN"] = "admin_pass_123"
os.environ["SEED_PASSWORD_SUPERVISOR"] = "supervisor_pass_123"
os.environ["SEED_PASSWORD_INVESTIGATOR"] = "investigator_pass_123"
os.environ["SEED_PASSWORD_ARTIST"] = "artist_pass_123"
os.environ["SEED_PASSWORD_AUDITOR"] = "auditor_pass_123"

import scripts.init_db as init_db_script
import scripts.seed_users as seed_users_script
from backend.app.core.config import Settings
from backend.app.core.security import create_access_token
from backend.app.db.session import get_connection, get_engine
from backend.app.main import create_app


@pytest.fixture(scope="function")
def test_db(tmp_path):
    db_file = tmp_path / "test_velora.db"
    init_db_script.init_db(db_file)
    seed_users_script.seed_users(db_file)
    db_url = f"sqlite:///{db_file}"

    test_engine = get_engine(db_url)

    def override_get_connection():
        with test_engine.connect() as conn:
            yield conn

    app = create_app()
    app.dependency_overrides[get_connection] = override_get_connection
    client = TestClient(app)

    return {"client": client, "db_file": db_file, "engine": test_engine, "app": app}


def test_tb1_1_login_and_lock(test_db):
    """
    TB1.1 login ok -> token with correct claims; wrong password -> 401 AUTH_INVALID;
    5 wrong attempts -> 6th (even with right password) -> 423;
    after setting locked_until in the past -> login works again.
    """
    client = test_db["client"]
    db_file = test_db["db_file"]

    # 1. Login OK
    resp = client.post("/api/v1/auth/login", json={"username": "investigator", "password": "investigator_pass_123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["role"] == "investigator"

    # 2. Wrong password -> 401 AUTH_INVALID
    resp_wrong = client.post("/api/v1/auth/login", json={"username": "investigator", "password": "wrong_password"})
    assert resp_wrong.status_code == 401
    assert resp_wrong.json()["error"]["code"] == "AUTH_INVALID"

    # 3. Fail 4 more times (total 5 failures)
    for _ in range(4):
        client.post("/api/v1/auth/login", json={"username": "investigator", "password": "wrong_password"})

    # 4. 6th attempt (even with right password) -> 423 ACCOUNT_LOCKED
    resp_6th = client.post("/api/v1/auth/login", json={"username": "investigator", "password": "investigator_pass_123"})
    assert resp_6th.status_code == 423, resp_6th.text
    assert resp_6th.json()["error"]["code"] == "ACCOUNT_LOCKED"

    # 5. Set locked_until in the past
    past_iso = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(str(db_file))
    conn.execute("UPDATE users SET locked_until = ? WHERE username = 'investigator'", (past_iso,))
    conn.commit()
    conn.close()

    # 6. Login works again
    resp_relogin = client.post("/api/v1/auth/login", json={"username": "investigator", "password": "investigator_pass_123"})
    assert resp_relogin.status_code == 200, resp_relogin.text
    assert "access_token" in resp_relogin.json()


def test_tb1_2_token_validation(test_db):
    """
    TB1.2 expired token -> 401 AUTH_EXPIRED; garbage token -> 401 AUTH_INVALID.
    """
    client = test_db["client"]

    # Expired token
    expired_token = create_access_token(sub="any-id", role="investigator", expires_minutes=-10)
    resp_exp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp_exp.status_code == 401, resp_exp.text
    assert resp_exp.json()["error"]["code"] == "AUTH_EXPIRED"

    # Garbage token
    resp_garb = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer this.is.garbage.token"})
    assert resp_garb.status_code == 401
    assert resp_garb.json()["error"]["code"] == "AUTH_INVALID"


def test_tb1_3_role_matrix(test_db):
    """
    TB1.3 role matrix table-driven: for each role x representative route
    (list users, create case, view case, audit view, glossary review, models list)
    assert allow/deny per §6.3.
    """
    client = test_db["client"]
    db_file = test_db["db_file"]

    # Create tokens for each role
    tokens = {}
    users_by_role = {}
    conn = sqlite3.connect(str(db_file))
    for role in ["admin", "supervisor", "investigator", "artist", "auditor"]:
        row = conn.execute("SELECT id, username, role FROM users WHERE role = ?", (role,)).fetchone()
        tokens[role] = create_access_token(sub=row[0], role=role)
        users_by_role[role] = row[0]

    # Create a test case
    case_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO cases (id, case_number, title, data_mode, default_appearance_group, status, created_by, created_at, updated_at)
        VALUES (?, 'FIR-101', 'Test Burglary', 'demo', 'unspecified', 'open', ?, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z')
        """,
        (case_id, users_by_role["supervisor"])
    )
    # Grant investigator view access, artist NO access
    conn.execute(
        """
        INSERT INTO case_access (id, case_id, user_id, access_level, granted_by, granted_at)
        VALUES (?, ?, ?, 'view', ?, '2026-10-28T00:00:00Z')
        """,
        (str(uuid.uuid4()), case_id, users_by_role["investigator"], users_by_role["supervisor"])
    )
    conn.commit()
    conn.close()

    # Table-driven matrix tests:
    # Route, Method, allowed_roles
    matrix = [
        # List users: admin only
        ("GET", "/api/v1/users", {}, ["admin"]),
        # Create case: investigator, supervisor
        ("POST", "/api/v1/cases", {"json": {"case_number": "FIR-NEW", "title": "New Case"}}, ["investigator", "supervisor"]),
        # View case: supervisor (all), investigator (with grant), auditor (metadata only). Artist (no grant) and Admin (no grant) denied
        ("GET", f"/api/v1/cases/{case_id}", {"headers": {"X-Access-Purpose": "investigation review"}}, ["supervisor", "investigator", "auditor"]),
        # Audit view: auditor, admin
        ("GET", "/api/v1/audit", {}, ["auditor", "admin"]),
        # Glossary review: supervisor, admin
        ("GET", "/api/v1/glossary", {}, ["supervisor", "admin"]),
        # Models list: admin, supervisor
        ("GET", "/api/v1/admin/models", {}, ["admin", "supervisor"]),
    ]

    for method, path, req_kwargs, allowed in matrix:
        for role in ["admin", "supervisor", "investigator", "artist", "auditor"]:
            headers = dict(req_kwargs.get("headers", {}))
            headers["Authorization"] = f"Bearer {tokens[role]}"
            kwargs = {k: v for k, v in req_kwargs.items() if k != "headers"}
            kwargs["headers"] = headers

            # Make case_number unique per role attempt if creating case
            if method == "POST" and path == "/api/v1/cases":
                kwargs["json"] = {"case_number": f"FIR-NEW-{role}-{uuid.uuid4().hex[:6]}", "title": f"New Case {role}"}

            if method == "GET":
                resp = client.get(path, **kwargs)
            else:
                resp = client.post(path, **kwargs)

            if role in allowed:
                assert resp.status_code in (200, 201), f"Role '{role}' expected ALLOW on {method} {path}, got {resp.status_code}: {resp.text}"
            else:
                assert resp.status_code == 403, f"Role '{role}' expected 403 FORBIDDEN on {method} {path}, got {resp.status_code}: {resp.text}"


def test_tb1_4_purpose_header(test_db):
    """
    TB1.4 case-scoped route without X-Access-Purpose -> 400; with 3 characters -> 400; with 5+ -> proceeds.
    """
    client = test_db["client"]
    db_file = test_db["db_file"]

    conn = sqlite3.connect(str(db_file))
    user_row = conn.execute("SELECT id, role FROM users WHERE role = 'supervisor'").fetchone()
    case_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO cases (id, case_number, title, data_mode, default_appearance_group, status, created_by, created_at, updated_at)
        VALUES (?, 'FIR-PURP-1', 'Purpose Test', 'demo', 'unspecified', 'open', ?, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z')
        """,
        (case_id, user_row[0])
    )
    conn.commit()
    conn.close()

    token = create_access_token(sub=user_row[0], role="supervisor")
    auth_header = {"Authorization": f"Bearer {token}"}

    # 1. No header -> 400 PURPOSE_REQUIRED
    r1 = client.get(f"/api/v1/cases/{case_id}", headers=auth_header)
    assert r1.status_code == 400
    assert r1.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 2. 3 characters -> 400 PURPOSE_REQUIRED
    r2 = client.get(f"/api/v1/cases/{case_id}", headers={**auth_header, "X-Access-Purpose": "abc"})
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 3. 5+ characters -> proceeds (200)
    r3 = client.get(f"/api/v1/cases/{case_id}", headers={**auth_header, "X-Access-Purpose": "valid purpose"})
    assert r3.status_code == 200


def test_tb1_5_idempotent_init_and_seed(tmp_path):
    """
    TB1.5 scripts/init_db.py twice is idempotent; scripts/seed_users.py with an
    empty seed password exits non-zero; passwords are stored as argon2 hashes ($argon2).
    """
    db_file = tmp_path / "idempotent.db"

    # 1. init_db twice is idempotent
    assert init_db_script.init_db(db_file) is True
    assert init_db_script.init_db(db_file) is True

    # 2. seed_users with empty seed password exits non-zero
    old_env = os.environ.get("SEED_PASSWORD_ADMIN")
    try:
        os.environ["SEED_PASSWORD_ADMIN"] = ""
        res_empty = seed_users_script.seed_users(db_file)
        assert res_empty is False
    finally:
        os.environ["SEED_PASSWORD_ADMIN"] = old_env

    # 3. seed_users with valid passwords stores argon2 hashes
    res_ok = seed_users_script.seed_users(db_file)
    assert res_ok is True

    conn = sqlite3.connect(str(db_file))
    hashes = [row[0] for row in conn.execute("SELECT password_hash FROM users").fetchall()]
    conn.close()
    assert len(hashes) == 5
    for h in hashes:
        assert h.startswith("$argon2")


def test_tb1_6_health_endpoint(test_db):
    """
    TB1.6 GET /health returns db:"ok" and shows ml_service/speech_service as
    down when they are not running (real connection attempts with 2 s timeout, not hard-coded).
    """
    client = test_db["client"]
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["db"] == "ok"
    assert data["ml_service"] == "down"
    assert data["speech_service"] == "down"
    assert "time" in data


def test_tb1_7_empty_jwt_secret_fails():
    """
    TB1.7 Starting the app with empty JWT_SECRET fails with a clear message.
    """
    bad_settings = Settings(JWT_SECRET="", SERVICE_KEY="valid_service_key_test")
    with pytest.raises(ValueError, match="JWT_SECRET must be at least 32 characters"):
        bad_settings.validate_secrets()
