import csv
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

# Set test environment variables before importing app
os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from backend.app.audit.chain import (  # noqa: E402
    verify_audit_chain,
    write_audit_entry,
)
from backend.app.core.config import settings  # noqa: E402

settings.SERVICE_KEY = os.environ["SERVICE_KEY"]
settings.JWT_SECRET = os.environ["JWT_SECRET"]

from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.db.session import set_engine  # noqa: E402
from backend.app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    # Initialize schema
    schema_sql = (ROOT / "contracts/schema.sql").read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    con.executescript(schema_sql)

    # Seed default users
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
    from backend.app.db.session import get_connection
    app.dependency_overrides[get_connection] = override_get_connection
    return TestClient(app)


def get_token(users: dict, role: str) -> str:
    user = users[role]
    return create_access_token(sub=user["id"], role=user["role"])


def test_tb2_1_sequential_100_entries(temp_db, client):
    """
    TB2.1: 100 sequential audited calls -> GET /audit/verify => {valid: true, checked: >=100};
    head_hash equals the last row's entry_hash.
    """
    engine = temp_db["engine"]

    for i in range(100):
        write_audit_entry(
            engine=engine,
            action="case.view",
            user_id="user-seq-1",
            username="seq_user",
            role="investigator",
            resource_type="case",
            resource_id=f"case-{i}",
            case_id=f"case-{i}",
            purpose="Routine case review",
            ip="127.0.0.1",
            user_agent="pytest/1.0",
            status_code=200,
            details={"index": i},
        )

    auditor_token = get_token(temp_db["users"], "auditor")
    res = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["valid"] is True
    assert data["checked"] >= 100

    # Verify head_hash matches the last row in DB
    with engine.connect() as conn:
        last_hash = conn.execute(
            text("SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1")
        ).scalar()

    assert data["head_hash"] == last_hash


def test_tb2_2_50_parallel_threads(temp_db):
    """
    TB2.2: 50 parallel requests (threads) -> seq contiguous, chain valid.
    """
    engine = temp_db["engine"]
    errors = []

    def worker(idx: int):
        try:
            write_audit_entry(
                engine=engine,
                action="session.view",
                user_id=f"user-{idx}",
                username=f"worker_{idx}",
                role="investigator",
                resource_type="session",
                resource_id=f"sess-{idx}",
                case_id="case-concurrent",
                purpose="Parallel audit test",
                ip="192.168.1.100",
                user_agent="pytest-thread/1.0",
                status_code=200,
                details={"worker_index": idx},
            )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors in concurrent writes: {errors}"

    # Verify sequence numbers are strictly contiguous
    with engine.connect() as conn:
        seqs = [r[0] for r in conn.execute(text("SELECT seq FROM audit_log ORDER BY seq ASC")).fetchall()]

    assert len(seqs) == 50
    assert seqs == list(range(1, 51))

    # Verify chain validity
    verify_res = verify_audit_chain(engine)
    assert verify_res["valid"] is True
    assert verify_res["checked"] == 50
    assert verify_res["first_bad_seq"] is None


def test_tb2_3_tamper_detection(temp_db, client):
    """
    TB2.3: Modify one row's details_json via raw SQL (after dropping the trigger in test DB)
    -> verify returns valid: false and first_bad_seq equals that row; modify a middle row's prev_hash -> invalid.
    """
    engine = temp_db["engine"]
    db_path = temp_db["path"]

    # Seed 5 valid entries
    for i in range(1, 6):
        write_audit_entry(
            engine=engine,
            action="case.view",
            user_id="user-1",
            username="investigator",
            role="investigator",
            resource_type="case",
            resource_id=f"case-{i}",
            case_id=f"case-{i}",
            purpose="Tamper verification testing",
            status_code=200,
            details={"step": i},
        )

    # 1. Modify details_json of row 3
    con = sqlite3.connect(str(db_path))
    con.execute("DROP TRIGGER IF EXISTS audit_no_update;")
    con.execute("UPDATE audit_log SET details_json = ? WHERE seq = 3", ('{"tampered": true}',))
    con.execute(
        """
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT
        RAISE(ABORT,'audit_log is append-only'); END;
        """
    )
    con.commit()
    con.close()

    res = verify_audit_chain(engine)
    assert res["valid"] is False
    assert res["first_bad_seq"] == 3

    # 2. Modify prev_hash of row 4
    con = sqlite3.connect(str(db_path))
    con.execute("DROP TRIGGER IF EXISTS audit_no_update;")
    con.execute("UPDATE audit_log SET prev_hash = ? WHERE seq = 4", ("1" * 64,))
    con.execute(
        """
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT
        RAISE(ABORT,'audit_log is append-only'); END;
        """
    )
    con.commit()
    con.close()

    res = verify_audit_chain(engine)
    assert res["valid"] is False
    # seq 3 is still bad; if seq 3 was restored, seq 4 would be the first bad seq
    assert res["first_bad_seq"] in (3, 4)


def test_tb2_4_append_only_triggers(temp_db):
    """
    TB2.4: UPDATE audit_log ... and DELETE FROM audit_log ... raise audit_log is append-only.
    """
    engine = temp_db["engine"]

    write_audit_entry(
        engine=engine,
        action="auth.login",
        user_id="user-1",
        username="admin",
        role="admin",
        status_code=200,
        details={},
    )

    with engine.connect() as conn:
        with pytest.raises(Exception) as exc_update:
            conn.execute(text("UPDATE audit_log SET action = 'tampered' WHERE seq = 1"))
        assert "audit_log is append-only" in str(exc_update.value)

        with pytest.raises(Exception) as exc_delete:
            conn.execute(text("DELETE FROM audit_log WHERE seq = 1"))
        assert "audit_log is append-only" in str(exc_delete.value)


def test_tb2_5_denied_case_access(temp_db, client):
    """
    TB2.5: Denied case access (investigator without grant) writes access.denied with the right case_id.
    """
    engine = temp_db["engine"]
    users = temp_db["users"]

    # Create a case directly
    case_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cases (id, case_number, title, station, status, created_by, created_at, updated_at)
                VALUES (:id, 'FIR-TB2-5', 'Test Case', 'Central', 'open', :cb, '2026-10-28T12:00:00.000Z', '2026-10-28T12:00:00.000Z')
                """
            ),
            {"id": case_id, "cb": users["supervisor"]["id"]},
        )

    # Investigator attempts to view case without grant
    inv_token = get_token(users, "investigator")
    res = client.get(
        f"/api/v1/cases/{case_id}",
        headers={
            "Authorization": f"Bearer {inv_token}",
            "X-Access-Purpose": "Trying unauthorized access",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    # Check audit log for access.denied record
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT action, case_id, resource_type, resource_id, purpose, status_code, role, username
                FROM audit_log
                WHERE action = 'access.denied' AND case_id = :case_id
                """
            ),
            {"case_id": case_id},
        ).mappings().fetchone()

    assert row is not None
    assert row["action"] == "access.denied"
    assert row["case_id"] == case_id
    assert row["resource_type"] == "case"
    assert row["resource_id"] == case_id
    assert row["purpose"] == "Trying unauthorized access"
    assert row["status_code"] == 403
    assert row["role"] == "investigator"
    assert row["username"] == "investigator"


def test_tb2_6_auditor_admin_rbac_and_export(temp_db, client):
    """
    TB2.6: Only auditor/admin can read /audit*; reading it writes audit.view;
    audit/export?format=csv returns a header row and the same count of entries as /audit for the same filters.
    """
    engine = temp_db["engine"]
    users = temp_db["users"]

    # 1. RBAC checks on /api/v1/audit
    for r in ["investigator", "artist", "supervisor"]:
        tok = get_token(users, r)
        res = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 403, f"Expected 403 for {r}"

    # 2. Seed 10 audit records with known actions
    for i in range(10):
        write_audit_entry(
            engine=engine,
            action="case.create" if i < 6 else "user.create",
            user_id=users["admin"]["id"],
            username="admin",
            role="admin",
            resource_type="case" if i < 6 else "user",
            resource_id=f"res-{i}",
            status_code=201,
            details={"index": i},
        )

    auditor_tok = get_token(users, "auditor")

    # 3. Reading /audit writes audit.view
    res_list = client.get(
        "/api/v1/audit?action=case.create",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert res_list.status_code == 200
    entries = res_list.json()
    assert len(entries) == 6

    # Verify audit.view was written
    with engine.connect() as conn:
        view_row = conn.execute(
            text("SELECT action, role, username FROM audit_log WHERE action = 'audit.view' ORDER BY seq DESC LIMIT 1")
        ).mappings().fetchone()
    assert view_row is not None
    assert view_row["role"] == "auditor"

    # 4. CSV Export returns header row + exact same count of entries for same filters
    res_csv = client.get(
        "/api/v1/audit/export?format=csv&action=case.create",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]

    csv_reader = csv.reader(io.StringIO(res_csv.text))
    csv_rows = list(csv_reader)
    header = csv_rows[0]
    data_rows = csv_rows[1:]

    assert "seq" in header
    assert "entry_hash" in header
    assert len(data_rows) == len(entries)

    # 5. JSON Export returns valid JSON array
    res_json = client.get(
        "/api/v1/audit/export?format=json&action=case.create",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    exported_json = res_json.json()
    assert len(exported_json) == len(entries)


def test_tb2_7_tamper_demo_script(temp_db, client):
    """
    TB2.7: tamper_demo.py --apply on a copy of the dev DB makes /audit/verify fail;
    --restore makes it pass again.
    """
    engine = temp_db["engine"]
    db_path = temp_db["path"]
    backup_path = db_path.parent / (db_path.stem + ".bak.db")

    # Seed 10 audit entries
    for i in range(10):
        write_audit_entry(
            engine=engine,
            action="case.view",
            user_id="user-1",
            username="investigator",
            role="investigator",
            resource_type="case",
            resource_id=f"case-{i}",
            case_id=f"case-{i}",
            purpose="Demonstration testing",
            status_code=200,
            details={"step": i},
        )

    # Initial verify must pass
    auditor_tok = get_token(temp_db["users"], "auditor")
    res_init = client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_init.status_code == 200
    assert res_init.json()["valid"] is True

    # Run tamper_demo.py --apply
    py_cmd = sys.executable
    tamper_script = str(ROOT / "scripts/tamper_demo.py")
    ret_apply = subprocess.run(
        [py_cmd, tamper_script, "--apply", "--db-path", str(db_path), "--backup-path", str(backup_path)],
        capture_output=True,
        text=True,
    )
    assert ret_apply.returncode == 0, f"tamper_demo --apply failed: {ret_apply.stderr}"

    # Verify must now fail
    res_tampered = client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_tampered.status_code == 200
    assert res_tampered.json()["valid"] is False
    assert res_tampered.json()["first_bad_seq"] is not None

    # Run tamper_demo.py --restore
    ret_restore = subprocess.run(
        [py_cmd, tamper_script, "--restore", "--db-path", str(db_path), "--backup-path", str(backup_path)],
        capture_output=True,
        text=True,
    )
    assert ret_restore.returncode == 0, f"tamper_demo --restore failed: {ret_restore.stderr}"

    # Verify must pass again
    res_restored = client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {auditor_tok}"})
    assert res_restored.status_code == 200
    assert res_restored.json()["valid"] is True


EXISTING_7_1_AUDITED_ENDPOINTS = [
    ("POST", "/api/v1/auth/login", "auth.login"),
    ("POST", "/api/v1/auth/login", "auth.login_failed"),
    ("POST", "/api/v1/auth/logout", "auth.logout"),
    ("POST", "/api/v1/users", "user.create"),
    ("PATCH", "/api/v1/users/{id}", "user.update"),
    ("POST", "/api/v1/cases", "case.create"),
    ("GET", "/api/v1/cases/{id}", "case.view"),
    ("GET", "/api/v1/audit", "audit.view"),
    ("GET", "/api/v1/audit/verify", "audit.verify"),
    ("GET", "/api/v1/audit/export", "audit.export"),
    ("GET", "/api/v1/cases/{id}", "access.denied"),
]


@pytest.mark.parametrize("method,path,expected_action", EXISTING_7_1_AUDITED_ENDPOINTS)
def test_tb2_8_all_existing_7_1_endpoints_audited(temp_db, client, method, path, expected_action):
    """
    TB2.8: A parametrized test lists every (method, path, audit_action) from the §7.1 table
    that already exists and asserts an audit row is written; the list grows with each later step.
    """
    engine = temp_db["engine"]
    users = temp_db["users"]

    admin_tok = get_token(users, "admin")
    auditor_tok = get_token(users, "auditor")
    supervisor_tok = get_token(users, "supervisor")
    investigator_tok = get_token(users, "investigator")

    # Helper to count rows for an action
    def count_action(act: str) -> int:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT COUNT(*) FROM audit_log WHERE action = :act"),
                {"act": act},
            ).scalar()

    before_count = count_action(expected_action)

    if expected_action == "auth.login":
        res = client.post("/api/v1/auth/login", json={"username": "admin", "password": users["admin"]["password"]})
        assert res.status_code == 200
    elif expected_action == "auth.login_failed":
        res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong_password_here"})
        assert res.status_code in (401, 423)
    elif expected_action == "auth.logout":
        res = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {admin_tok}"})
        assert res.status_code == 200
    elif expected_action == "user.create":
        uname = f"u_{uuid.uuid4().hex[:6]}"
        res = client.post(
            "/api/v1/users",
            json={"username": uname, "full_name": "Test User", "role": "investigator", "password": "UserPass12345!"},
            headers={"Authorization": f"Bearer {admin_tok}"},
        )
        assert res.status_code == 201
    elif expected_action == "user.update":
        target_uid = users["artist"]["id"]
        res = client.patch(
            f"/api/v1/users/{target_uid}",
            json={"full_name": "Updated Artist Name"},
            headers={"Authorization": f"Bearer {admin_tok}"},
        )
        assert res.status_code == 200
    elif expected_action == "case.create":
        cnum = f"FIR-{uuid.uuid4().hex[:6]}"
        res = client.post(
            "/api/v1/cases",
            json={"case_number": cnum, "title": "Audit Test Case"},
            headers={"Authorization": f"Bearer {supervisor_tok}"},
        )
        assert res.status_code == 201
    elif expected_action == "case.view":
        # Create case first, supervisor can view all cases
        cnum = f"FIR-{uuid.uuid4().hex[:6]}"
        c_res = client.post(
            "/api/v1/cases",
            json={"case_number": cnum, "title": "View Test Case"},
            headers={"Authorization": f"Bearer {supervisor_tok}"},
        )
        cid = c_res.json()["id"]
        res = client.get(
            f"/api/v1/cases/{cid}",
            headers={"Authorization": f"Bearer {supervisor_tok}", "X-Access-Purpose": "Viewing case for audit"},
        )
        assert res.status_code == 200
    elif expected_action == "audit.view":
        res = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {auditor_tok}"})
        assert res.status_code == 200
    elif expected_action == "audit.verify":
        res = client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {auditor_tok}"})
        assert res.status_code == 200
    elif expected_action == "audit.export":
        res = client.get("/api/v1/audit/export?format=json", headers={"Authorization": f"Bearer {auditor_tok}"})
        assert res.status_code == 200
    elif expected_action == "access.denied":
        # Create case with supervisor, attempt access with investigator without grant
        cnum = f"FIR-{uuid.uuid4().hex[:6]}"
        c_res = client.post(
            "/api/v1/cases",
            json={"case_number": cnum, "title": "Denied Access Case"},
            headers={"Authorization": f"Bearer {supervisor_tok}"},
        )
        cid = c_res.json()["id"]
        res = client.get(
            f"/api/v1/cases/{cid}",
            headers={"Authorization": f"Bearer {investigator_tok}", "X-Access-Purpose": "Unauthorized view"},
        )
        assert res.status_code == 403

    after_count = count_action(expected_action)
    assert after_count > before_count, f"Expected {expected_action} audit count to increase (before={before_count}, after={after_count})"


def test_tb2_9_csv_formula_injection_sanitization(temp_db, client):
    """
    Hardening: Verify CSV export sanitizes spreadsheet formula markers (=, +, -, @)
    while preserving original DB values and valid quoting.
    """
    engine = temp_db["engine"]
    users = temp_db["users"]
    auditor_tok = get_token(users, "auditor")

    # Seed an entry with formula characters in purpose and user_agent
    write_audit_entry(
        engine=engine,
        action="case.view",
        user_id="user-formula",
        username="formula_tester",
        role="investigator",
        resource_type="case",
        resource_id="case-formula-1",
        case_id="case-formula-1",
        purpose="=cmd|' /C calc'!A0",
        user_agent="+Mozilla/5.0",
        status_code=200,
        details={"formula_field": "@SUM(1,2)", "negative_num": -42},
    )

    # Seed an entry with ordinary text
    write_audit_entry(
        engine=engine,
        action="case.view",
        user_id="user-normal",
        username="normal_tester",
        role="investigator",
        resource_type="case",
        resource_id="case-normal-1",
        case_id="case-normal-1",
        purpose="Regular non-formula purpose",
        user_agent="NormalBrowser/1.0",
        status_code=200,
        details={"normal_field": "safe text"},
    )

    # 1. Export CSV
    res_csv = client.get(
        "/api/v1/audit/export?format=csv",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert res_csv.status_code == 200

    csv_rows = list(csv.reader(io.StringIO(res_csv.text)))
    header = csv_rows[0]
    purpose_idx = header.index("purpose")
    user_agent_idx = header.index("user_agent")
    case_id_idx = header.index("case_id")

    formula_row = next(r for r in csv_rows[1:] if r[case_id_idx] == "case-formula-1")
    normal_row = next(r for r in csv_rows[1:] if r[case_id_idx] == "case-normal-1")

    # Formula row cells must be prefixed with single quote in exported CSV
    assert formula_row[purpose_idx].startswith("'=")
    assert formula_row[purpose_idx] == "'=cmd|' /C calc'!A0"
    assert formula_row[user_agent_idx].startswith("'+")
    assert formula_row[user_agent_idx] == "'+Mozilla/5.0"

    # Normal row cells must NOT be prefixed
    assert normal_row[purpose_idx] == "Regular non-formula purpose"
    assert not normal_row[purpose_idx].startswith("'")
    assert normal_row[user_agent_idx] == "NormalBrowser/1.0"

    # 2. Verify original database values are completely untouched
    with engine.connect() as conn:
        db_row = conn.execute(
            text("SELECT purpose, user_agent FROM audit_log WHERE case_id = 'case-formula-1'")
        ).mappings().fetchone()
    assert db_row["purpose"] == "=cmd|' /C calc'!A0"
    assert db_row["user_agent"] == "+Mozilla/5.0"


def test_tb2_10_empty_chain_and_malformed_json(temp_db):
    """
    Hardening: Verify empty chain returns documented empty result,
    and malformed JSON in details_json causes verification failure with first_bad_seq.
    """
    engine = temp_db["engine"]
    db_path = temp_db["path"]

    # 1. Empty chain check
    empty_res = verify_audit_chain(engine)
    assert empty_res == {
        "valid": True,
        "checked": 0,
        "first_bad_seq": None,
        "head_hash": None,
    }

    # 2. Seed 3 valid entries
    for i in range(1, 4):
        write_audit_entry(
            engine=engine,
            action="case.view",
            user_id="user-1",
            username="investigator",
            role="investigator",
            resource_type="case",
            resource_id=f"case-{i}",
            case_id=f"case-{i}",
            purpose="Testing malformed json",
            status_code=200,
            details={"step": i},
        )

    assert verify_audit_chain(engine)["valid"] is True

    # 3. Corrupt details_json of row 2 with malformed (unparseable) JSON
    con = sqlite3.connect(str(db_path))
    con.execute("DROP TRIGGER IF EXISTS audit_no_update;")
    con.execute("UPDATE audit_log SET details_json = ? WHERE seq = 2", ("{unclosed-malformed-json: [",))
    con.execute(
        """
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT
        RAISE(ABORT,'audit_log is append-only'); END;
        """
    )
    con.commit()
    con.close()

    corrupt_res = verify_audit_chain(engine)
    assert corrupt_res["valid"] is False
    assert corrupt_res["first_bad_seq"] == 2


def test_tb2_11_audit_endpoints_comprehensive_rbac(temp_db, client):
    """
    Hardening: Confirm unauthorized roles cannot access any of the 3 audit endpoints,
    and unauthorized access attempts do not cause recursive or inappropriate audit writes.
    """
    engine = temp_db["engine"]
    users = temp_db["users"]

    unauthorized_roles = ["investigator", "artist", "supervisor"]
    endpoints = [
        ("GET", "/api/v1/audit"),
        ("GET", "/api/v1/audit/verify"),
        ("GET", "/api/v1/audit/export?format=json"),
        ("GET", "/api/v1/audit/export?format=csv"),
    ]

    for role in unauthorized_roles:
        token = get_token(users, role)
        headers = {"Authorization": f"Bearer {token}"}

        for method, path in endpoints:
            before_count = _count_audit_rows(engine)
            res = client.request(method, path, headers=headers)
            assert res.status_code == 403, f"Expected 403 for role={role} on {path}, got {res.status_code}"
            assert res.json()["error"]["code"] == "FORBIDDEN"
            after_count = _count_audit_rows(engine)

            # Audit endpoints are not case-scoped, so rejected audit reads must not write audit entries
            assert after_count == before_count, f"Forbidden access on {path} by {role} created unexpected audit row"


def test_tb2_12_transaction_failure_recovery(temp_db):
    """
    Hardening: Simulate an audit write failure and verify:
    - No partial/corrupted audit row is left behind (rollback works).
    - Database remains usable.
    - Subsequent write produces a valid chain with contiguous sequence numbers.
    """
    engine = temp_db["engine"]
    db_path = temp_db["path"]

    # 1. Seed 2 initial rows
    write_audit_entry(engine=engine, action="auth.login", username="u1", role="admin", status_code=200)
    write_audit_entry(engine=engine, action="case.create", case_id="c1", username="u1", role="admin", status_code=201)

    initial_check = verify_audit_chain(engine)
    assert initial_check["valid"] is True
    assert initial_check["checked"] == 2

    # 2. Add a trigger that deliberately aborts writes with action='auth.logout'
    con = sqlite3.connect(str(db_path))
    con.execute(
        """
        CREATE TRIGGER test_simulate_failure BEFORE INSERT ON audit_log
        WHEN NEW.action = 'auth.logout'
        BEGIN
            SELECT RAISE(ABORT, 'Simulated disk/constraint write failure');
        END;
        """
    )
    con.commit()
    con.close()

    # 3. Attempt write that will fail
    with pytest.raises(Exception) as exc_info:
        write_audit_entry(engine=engine, action="auth.logout", username="u1", role="admin", status_code=200)
    assert "Simulated disk/constraint write failure" in str(exc_info.value)

    # 4. Assert rollback: exactly 2 rows remain
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM audit_log")).scalar()
        seqs = [r[0] for r in conn.execute(text("SELECT seq FROM audit_log ORDER BY seq ASC")).fetchall()]
    assert count == 2
    assert seqs == [1, 2]

    # 5. Remove the failure trigger
    con = sqlite3.connect(str(db_path))
    con.execute("DROP TRIGGER IF EXISTS test_simulate_failure;")
    con.commit()
    con.close()

    # 6. Database remains usable: subsequent write succeeds with contiguous sequence seq=3
    entry3 = write_audit_entry(
        engine=engine,
        action="case.view",
        case_id="c1",
        username="u1",
        role="admin",
        status_code=200,
    )
    assert entry3["seq"] == 3

    # 7. Chain remains fully valid
    final_check = verify_audit_chain(engine)
    assert final_check["valid"] is True
    assert final_check["checked"] == 3
    assert final_check["head_hash"] == entry3["entry_hash"]


def _count_audit_rows(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM audit_log")).scalar()
