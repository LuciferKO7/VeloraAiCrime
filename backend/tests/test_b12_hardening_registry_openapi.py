import json
import logging
import os
import sqlite3
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

from backend.app.core.logging import SensitiveDataFilter, sanitize_log_message  # noqa: E402
from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.db.session import get_connection, set_engine  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.services.registry_sync import sync_model_registry  # noqa: E402
from scripts.backup_db import backup_database  # noqa: E402
from scripts.backup_db import main as backup_main  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def temp_db(tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    schema_sql = (ROOT / "contracts/schema.sql").read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    con.executescript(schema_sql)

    now = "2026-10-28T12:00:00.000Z"
    # Seed users (roles: investigator, artist, supervisor, auditor, admin)
    admin_id = str(uuid.uuid4())
    investigator_id = str(uuid.uuid4())
    pw_hash = hash_password("Password123!")

    con.execute(
        """
        INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (admin_id, "admin_user", "Admin User", "admin", pw_hash, now),
    )
    con.execute(
        """
        INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (investigator_id, "investigator_user", "Investigator User", "investigator", pw_hash, now),
    )
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    set_engine(engine)

    app = create_app()

    def override_get_connection():
        with engine.connect() as connection:
            yield connection

    app.dependency_overrides[get_connection] = override_get_connection

    admin_token = create_access_token(admin_id, "admin")
    investigator_token = create_access_token(investigator_id, "investigator")

    client = TestClient(app)

    yield {
        "engine": engine,
        "db_path": db_path,
        "client": client,
        "admin_token": admin_token,
        "investigator_token": investigator_token,
        "admin_id": admin_id,
        "investigator_id": investigator_id,
    }

    engine.dispose()
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_tb12_1_registry_sync_idempotency_and_exclusive_activation(temp_db):
    """
    TB12.1: Model registry startup sync and exclusive per-role activation (§8.0, Step B12).
    - Syncing populates model registry idempotently without duplicate error.
    - Exclusive activation deactivates all other models for that role in a single transaction.
    - Generates hash-chained audit entry for admin.model_activate.
    - Enforces admin-only RBAC.
    """
    engine = temp_db["engine"]
    client = temp_db["client"]
    admin_token = temp_db["admin_token"]
    investigator_token = temp_db["investigator_token"]

    # 1. Sync registry twice to test idempotency
    models1 = sync_model_registry(engine)
    assert len(models1) > 0
    models2 = sync_model_registry(engine)
    assert len(models2) == len(models1)

    # 2. Seed two models with the same role: 'image_gen'
    id_a = str(uuid.uuid4())
    id_b = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_registry (id, name, role, version, source, license, is_active, registered_at)
                VALUES
                    (:id_a, 'sdxl-base-v1', 'image_gen', '1.0', 'huggingface', 'OpenRAIL', 1, '2026-10-28T12:00:00Z'),
                    (:id_b, 'sdxl-turbo-v1', 'image_gen', '1.0', 'huggingface', 'OpenRAIL', 0, '2026-10-28T12:00:00Z')
                """
            ),
            {"id_a": id_a, "id_b": id_b},
        )

    # 3. RBAC check: non-admin (investigator) cannot activate models
    resp_investigator = client.post(
        f"/api/v1/admin/models/{id_b}/activate",
        headers={"Authorization": f"Bearer {investigator_token}"},
    )
    assert resp_investigator.status_code == 403

    # 4. Exclusive activation: admin activates model B
    resp_admin = client.post(
        f"/api/v1/admin/models/{id_b}/activate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin.status_code == 200, resp_admin.text
    data = resp_admin.json()
    assert data["id"] == id_b
    assert data["is_active"] == 1

    # Verify model A was deactivated and model B is active
    with engine.connect() as conn:
        row_a = conn.execute(text("SELECT is_active FROM model_registry WHERE id = :id"), {"id": id_a}).scalar()
        row_b = conn.execute(text("SELECT is_active FROM model_registry WHERE id = :id"), {"id": id_b}).scalar()
        assert row_a == 0
        assert row_b == 1

        # Verify audit log entry
        audit_row = conn.execute(
            text("SELECT action, resource_type, resource_id, username FROM audit_log WHERE action = 'admin.model_activate'"),
        ).mappings().fetchone()
        assert audit_row is not None
        assert audit_row["resource_id"] == id_b
        assert audit_row["username"] == "admin_user"

    # 5. Activating non-existent model returns 404
    resp_404 = client.post(
        f"/api/v1/admin/models/{uuid.uuid4()}/activate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_404.status_code == 404


def test_tb12_2_request_size_limits(temp_db):
    """
    TB12.2: Enforce request size limits with 413 REQUEST_TOO_LARGE (§12 Step B12).
    - Standard JSON requests > 2MB rejected with 413.
    - Multipart / upload requests > 15MB rejected with 413.
    - Normal payload succeeds.
    """
    client = temp_db["client"]
    admin_token = temp_db["admin_token"]

    # 1. Normal JSON request (< 2MB)
    resp_ok = client.post(
        "/api/v1/admin/eval-runs",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
        json={"kind": "parser", "config": {}, "metrics": {"precision": 0.95}},
    )
    assert resp_ok.status_code == 201

    # 2. Oversized JSON request (> 2MB limit)
    # 2.5 MB body
    large_payload = "a" * (2500 * 1024)
    resp_large = client.post(
        "/api/v1/admin/eval-runs",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "Content-Length": str(len(large_payload)),
        },
        content=large_payload,
    )
    assert resp_large.status_code == 413
    data = resp_large.json()
    assert data["error"]["code"] == "REQUEST_TOO_LARGE"

    # 3. Oversized upload request (> 15MB limit)
    oversized_upload_bytes = 16 * 1024 * 1024
    resp_upload_large = client.post(
        "/api/v1/cases/case-123/faces",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "multipart/form-data; boundary=testboundary",
            "Content-Length": str(oversized_upload_bytes),
        },
        content=b"",
    )
    assert resp_upload_large.status_code == 413
    data_upload = resp_upload_large.json()
    assert data_upload["error"]["code"] == "REQUEST_TOO_LARGE"


def test_tb12_3_security_headers(temp_db):
    """
    TB12.3: Security headers present on all responses (§12 Step B12).
    """
    client = temp_db["client"]
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200

    headers = resp.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-xss-protection") == "1; mode=block"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in headers.get("content-security-policy", "")


def test_tb12_4_logging_hygiene():
    """
    TB12.4: Structured logging hygiene and sensitive data redaction (§12 Step B12).
    - Passwords, JWTs, Bearer tokens, and base64 blobs must be redacted.
    - Event names and safe metadata remain intact.
    """
    # 1. Test string sanitizer directly
    jwt_sample = create_access_token("test-user-id", "investigator")
    bearer_sample = f"Bearer {jwt_sample}"
    password_sample = '{"username": "officer1", "password": "super_secret_password_123"}'
    base64_sample = "data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk" * 5

    assert "[JWT_REDACTED]" in sanitize_log_message(jwt_sample)
    assert "Bearer [REDACTED]" in sanitize_log_message(bearer_sample)
    assert '"password": "[REDACTED]"' in sanitize_log_message(password_sample)
    assert "data:image/...;base64,[REDACTED]" in sanitize_log_message(base64_sample)

    # 2. Test SensitiveDataFilter on logging.LogRecord
    record = logging.LogRecord(
        name="velora",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="User login attempt with token %s and password %s",
        args=(jwt_sample, "pass=Secret123"),
        exc_info=None,
    )
    s_filter = SensitiveDataFilter()
    s_filter.filter(record)
    formatted = record.msg % record.args
    assert "super_secret" not in formatted
    assert jwt_sample not in formatted


def test_tb12_5_backup_db_script(temp_db, tmp_path):
    """
    TB12.5: Database backup script online backup and safety (§12 Step B12).
    - Online backup using sqlite3.Connection.backup() copies data accurately.
    - Rejects missing source database with FileNotFoundError.
    - Rejects attempt to overwrite source database with ValueError.
    - CLI main() executes cleanly and returns exit code 0.
    """
    db_path = temp_db["db_path"]
    backup_file = tmp_path / "velora_backup_test.db"

    # 1. Direct function call
    result = backup_database(db_path, backup_file)
    assert result.exists()
    assert result.stat().st_size > 0

    # Verify backup is a valid SQLite DB with the same tables
    backup_conn = sqlite3.connect(str(backup_file))
    cursor = backup_conn.cursor()
    cursor.execute("SELECT count(*) FROM users")
    user_count = cursor.fetchone()[0]
    assert user_count == 2
    backup_conn.close()

    # 2. Error handling: missing source
    non_existent = tmp_path / "does_not_exist.db"
    with pytest.raises(FileNotFoundError):
        backup_database(non_existent, backup_file)

    # 3. Error handling: cannot overwrite source
    with pytest.raises(ValueError, match="Cannot overwrite source"):
        backup_database(db_path, db_path)

    # 4. CLI test
    cli_out = tmp_path / "velora_cli_backup.db"
    with patch("sys.argv", ["backup_db.py", "--db-path", str(db_path), "--output", str(cli_out)]):
        code = backup_main()
        assert code == 0
        assert cli_out.exists()


def test_tb12_6_openapi_schema():
    """
    TB12.6: OpenAPI schema export valid and contains all Person B routes (§12 Step B12).
    """
    openapi_path = ROOT / "docs/openapi.json"
    assert openapi_path.exists(), "docs/openapi.json must exist"

    data = json.loads(openapi_path.read_text(encoding="utf-8"))
    assert data["openapi"].startswith("3.")
    assert "paths" in data

    paths = data["paths"]
    # Check essential Person B routes
    expected_routes = [
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/v1/cases",
        "/api/v1/cases/{case_id}/witnesses",
        "/api/v1/cases/{case_id}/sessions",
        "/api/v1/audit",
        "/api/v1/glossary",
        "/api/v1/admin/models",
        "/api/v1/admin/models/{model_id}/activate",
        "/api/v1/gallery",
        "/api/v1/match",
        "/api/v1/match/search",
    ]

    for route in expected_routes:
        assert route in paths, f"Expected route {route} not found in openapi.json"
