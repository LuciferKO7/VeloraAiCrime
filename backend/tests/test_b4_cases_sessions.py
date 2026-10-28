import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any

# Set test environment variables before importing app
os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import settings

settings.SERVICE_KEY = os.environ["SERVICE_KEY"]
settings.JWT_SECRET = os.environ["JWT_SECRET"]

from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.db.session import get_connection, set_engine  # noqa: E402
from backend.app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


class AssumptionItem(BaseModel):
    key: str
    value: Any = None
    reason: str


class ImageUrls(BaseModel):
    photo: str
    pencil: str
    thumb: str


class RoundImage(BaseModel):
    id: str
    round_id: str
    parent_image_id: str | None = None
    variant_index: int
    kind: str
    width: int
    height: int
    seed: int | None = None
    variant_axes: dict[str, Any] = Field(default_factory=dict)
    attr_adherence: float | None = None
    identity_similarity: float | None = None
    speculative: bool = False
    is_final: bool = False
    has_sketch: bool = False
    urls: ImageUrls
    model_versions: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SessionRound(BaseModel):
    id: str
    session_id: str
    round_no: int
    kind: str
    status: str
    params: dict[str, Any] = Field(default_factory=dict)
    images: list[RoundImage] = Field(default_factory=list)
    error: str | None = None
    created_at: str
    finished_at: str | None = None


class SessionStateValidator(BaseModel):
    id: str
    case_id: str
    witness_id: str
    kind: str
    status: str
    current_round: int
    attributes: dict[str, Any]
    assumptions: list[AssumptionItem]
    locked_features: list[Any]
    selected_image_id: str | None = None
    statements: list[dict[str, Any]]
    rounds: list[SessionRound]
    created_at: str
    updated_at: str


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


def test_tb4_1_full_workflow_and_session_state(temp_db, client):
    """
    TB4.1: Investigator creates demo case, granted access by supervisor, creates Tamil witness,
    creates session, fetches GET /sessions/{sid} and validates full SessionState per §7.1 and §8.5.
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    inv_tok = get_token(users, "investigator")
    sup_tok = get_token(users, "supervisor")
    purpose = "TB4.1 full workflow verification test"

    # 1. Investigator creates demo case
    case_payload = {
        "case_number": "FIR-2026-TB4-001",
        "title": "Chennai Commercial Robbery Case",
        "station": "Anna Nagar Police Station",
        "offence_summary": "Robbery reported with two unidentified suspects",
        "data_mode": "demo",
        "default_appearance_group": "south_asian",
    }
    res_c = client.post(
        "/api/v1/cases",
        json=case_payload,
        headers={"Authorization": f"Bearer {inv_tok}"},
    )
    assert res_c.status_code == 201, res_c.text
    case_data = res_c.json()
    case_id = case_data["id"]
    assert case_data["case_number"] == case_payload["case_number"]
    assert case_data["data_mode"] == "demo"
    assert case_data["default_appearance_group"] == "south_asian"

    # 2. Supervisor grants investigator edit access to this case
    res_grant = client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": users["investigator"]["id"], "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert res_grant.status_code == 201, res_grant.text
    assert res_grant.json()["access_level"] == "edit"

    # 3. Investigator creates a witness with Tamil language
    res_w = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "W-TAMIL-01", "preferred_language": "ta"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_w.status_code == 201, res_w.text
    w_data = res_w.json()
    witness_id = w_data["id"]
    assert w_data["alias"] == "W-TAMIL-01"
    assert w_data["preferred_language"] == "ta"

    # 4. Investigator creates a face session
    res_s = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": witness_id, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_s.status_code == 201, res_s.text
    s_data = res_s.json()
    session_id = s_data["id"]
    assert s_data["status"] == "active"
    assert s_data["current_round"] == 0

    # 5. Fetch GET /sessions/{sid} and validate SessionState
    res_state = client.get(
        f"/api/v1/sessions/{session_id}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_state.status_code == 200, res_state.text
    raw_state = res_state.json()

    # Validate with strict Pydantic model
    validated = SessionStateValidator.model_validate(raw_state)
    assert validated.id == session_id
    assert validated.case_id == case_id
    assert validated.witness_id == witness_id
    assert validated.kind == "face"
    assert validated.status == "active"
    assert validated.current_round == 0
    assert validated.selected_image_id is None
    assert len(validated.statements) == 0
    assert len(validated.rounds) == 0

    # Verify assumptions panel (§8.5): 19 salient keys, all not_stated_varied_across_variants
    assert len(validated.assumptions) == 19
    for asm in validated.assumptions:
        assert asm.value is None
        assert asm.reason == "not_stated_varied_across_variants"

    # 6. Now populate attribute snapshot and a round with an image to verify full enrichment
    snap_id = str(uuid.uuid4())
    now_iso = "2026-10-28T12:05:00.000Z"
    sample_attributes = {
        "schema_version": "1.0",
        "attributes": {
            "face_shape": {"value": "oval", "confidence": 0.9, "source": "explicit"},
            "age_band": {"value": "30-35", "confidence": 0.8, "source": "inferred"},
        },
        "unmapped_notes": ["witness noted high cheekbones"],
    }

    round_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO attribute_snapshots (id, session_id, version, change_source, attributes_json, created_at)
                VALUES (:id, :sid, 1, 'statement', :json_str, :now)
                """
            ),
            {"id": snap_id, "sid": session_id, "json_str": json.dumps(sample_attributes), "now": now_iso},
        )
        conn.execute(
            text(
                """
                UPDATE sessions
                SET current_snapshot_id = :snap_id, current_round = 1, locked_features_json = '["hair_color"]'
                WHERE id = :sid
                """
            ),
            {"snap_id": snap_id, "sid": session_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO rounds (id, session_id, round_no, kind, status, params_json, attribute_snapshot_id, created_by, created_at)
                VALUES (:rid, :sid, 1, 'initial', 'done', '{}', :snap_id, :uid, :now)
                """
            ),
            {"rid": round_id, "sid": session_id, "snap_id": snap_id, "uid": users["investigator"]["id"], "now": now_iso},
        )
        conn.execute(
            text(
                """
                INSERT INTO images (
                    id, session_id, round_id, variant_index, kind, width, height, seed,
                    sha256, storage_path, sketch_path, speculative, is_final, created_at
                ) VALUES (
                    :img_id, :sid, :rid, 0, 'variant', 512, 512, 42,
                    'dummy_sha256_hash_value', 'storage/photos/sample.png', 'storage/sketches/sample.png', 0, 0, :now
                )
                """
            ),
            {"img_id": image_id, "sid": session_id, "rid": round_id, "now": now_iso},
        )

    # Re-fetch GET /sessions/{sid}
    res_enriched = client.get(
        f"/api/v1/sessions/{session_id}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_enriched.status_code == 200
    val_enriched = SessionStateValidator.model_validate(res_enriched.json())

    assert val_enriched.current_round == 1
    assert val_enriched.locked_features == ["hair_color"]
    assert len(val_enriched.rounds) == 1
    assert len(val_enriched.rounds[0].images) == 1

    img = val_enriched.rounds[0].images[0]
    assert img.id == image_id
    assert img.has_sketch is True
    assert img.urls.photo == f"/api/v1/images/{image_id}/file?style=photo"
    assert img.urls.pencil == f"/api/v1/images/{image_id}/file?style=pencil"
    assert img.urls.thumb == f"/api/v1/images/{image_id}/file?style=photo&size=thumb"

    # Check assumptions:
    # 1. face_shape was explicit -> omitted from assumptions
    # 2. age_band was inferred -> included with reason inferred_from_wording
    # 3. other 17 salient keys -> not_stated_varied_across_variants
    asm_map = {item.key: item for item in val_enriched.assumptions}
    assert "face_shape" not in asm_map
    assert "age_band" in asm_map
    assert asm_map["age_band"].value == "30-35"
    assert asm_map["age_band"].reason == "inferred_from_wording"
    assert len(val_enriched.assumptions) == 18


def test_tb4_2_validation_and_uniqueness(temp_db, client):
    """
    TB4.2: Duplicate case_number returns 422 VALIDATION_ERROR;
    invalid preferred_language returns 422 VALIDATION_ERROR;
    invalid session kind returns 422 VALIDATION_ERROR;
    duplicate witness alias in same case returns 422 VALIDATION_ERROR;
    auto-alias assigns collision-free W-001, W-002.
    """
    users = temp_db["users"]
    sup_tok = get_token(users, "supervisor")
    purpose = "TB4.2 validation and uniqueness testing"

    # 1. Create first case
    c1_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-DUP-001", "title": "Unique Case"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert c1_res.status_code == 201
    case_id = c1_res.json()["id"]

    # 2. Duplicate case_number -> 422
    c2_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-DUP-001", "title": "Duplicate Case"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert c2_res.status_code == 422
    err2 = c2_res.json()["error"]
    assert err2["code"] == "VALIDATION_ERROR"
    assert "already exists" in err2["message"]

    # 3. Invalid data_mode -> 422
    bad_mode_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-BAD-MODE", "title": "Bad Mode", "data_mode": "unsupported_mode"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert bad_mode_res.status_code == 422
    assert bad_mode_res.json()["error"]["code"] == "VALIDATION_ERROR"

    # 4. Invalid default_appearance_group -> 422
    bad_group_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-BAD-GRP", "title": "Bad Group", "default_appearance_group": "martian"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert bad_group_res.status_code == 422
    assert bad_group_res.json()["error"]["code"] == "VALIDATION_ERROR"

    # 5. Invalid preferred_language -> 422
    bad_lang_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"preferred_language": "klingon"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert bad_lang_res.status_code == 422
    err_lang = bad_lang_res.json()["error"]
    assert err_lang["code"] == "VALIDATION_ERROR"
    assert "Invalid preferred_language" in err_lang["message"]

    # 6. Auto-generated witness alias
    w1_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"preferred_language": "en"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert w1_res.status_code == 201
    w1_data = w1_res.json()
    assert w1_data["alias"] == "W-001"
    wid1 = w1_data["id"]

    w2_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"preferred_language": "hi"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert w2_res.status_code == 201
    w2_data = w2_res.json()
    assert w2_data["alias"] == "W-002"

    # 7. Duplicate witness alias in same case -> 422
    dup_alias_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "W-001", "preferred_language": "te"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert dup_alias_res.status_code == 422
    assert dup_alias_res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "already exists in this case" in dup_alias_res.json()["error"]["message"]

    # 8. Invalid session kind -> 422
    bad_kind_res = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid1, "kind": "vehicle"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert bad_kind_res.status_code == 422
    assert bad_kind_res.json()["error"]["code"] == "VALIDATION_ERROR"

    # 9. Non-existent witness -> 404
    missing_w_res = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": str(uuid.uuid4()), "kind": "face"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert missing_w_res.status_code == 404
    assert missing_w_res.json()["error"]["code"] == "NOT_FOUND"


def test_tb4_3_role_restrictions_and_auditor_prohibition(temp_db, client):
    """
    TB4.3:
    - Auditor GET /cases/{id} returns metadata only (no offence_summary or station).
    - Auditor GET /sessions/{sid} returns 403 FORBIDDEN and writes access.denied.
    - Admin without grant returns 403 FORBIDDEN.
    - Supervisor returns 200 on all cases and sessions.
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    sup_tok = get_token(users, "supervisor")
    aud_tok = get_token(users, "auditor")
    adm_tok = get_token(users, "admin")
    purpose = "TB4.3 role restrictions and auditor prohibition testing"

    # Supervisor creates case with sensitive offence_summary and station
    c_res = client.post(
        "/api/v1/cases",
        json={
            "case_number": "FIR-CONF-999",
            "title": "High Profile Investigation",
            "station": "Cyber Intelligence Unit",
            "offence_summary": "Top secret details regarding intercepted communications",
            "data_mode": "demo",
        },
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert c_res.status_code == 201
    case_id = c_res.json()["id"]

    # Supervisor creates witness and session
    w_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"preferred_language": "en"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    wid = w_res.json()["id"]

    s_res = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    sid = s_res.json()["id"]

    # 1. Supervisor GET case -> full access including offence_summary and station
    sup_case = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert sup_case.status_code == 200
    assert sup_case.json()["offence_summary"] == "Top secret details regarding intercepted communications"
    assert sup_case.json()["station"] == "Cyber Intelligence Unit"

    # 2. Supervisor GET session -> full 200
    sup_session = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert sup_session.status_code == 200

    # 3. Auditor GET case -> metadata only, offence_summary and station stripped
    aud_case = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {aud_tok}", "X-Access-Purpose": purpose},
    )
    assert aud_case.status_code == 200
    aud_case_data = aud_case.json()
    assert aud_case_data["id"] == case_id
    assert aud_case_data["case_number"] == "FIR-CONF-999"
    assert aud_case_data["title"] == "High Profile Investigation"
    assert "offence_summary" not in aud_case_data or aud_case_data["offence_summary"] is None
    assert "station" not in aud_case_data or aud_case_data["station"] is None

    # 4. Auditor GET session -> 403 FORBIDDEN and access.denied audit written
    aud_session = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {aud_tok}", "X-Access-Purpose": purpose},
    )
    assert aud_session.status_code == 403
    assert aud_session.json()["error"]["code"] == "FORBIDDEN"

    # 4b. Auditor GET /cases/{id}/sessions -> 403 FORBIDDEN and access.denied audit written (§6.3, TB4.3)
    aud_case_sessions = client.get(
        f"/api/v1/cases/{case_id}/sessions",
        headers={"Authorization": f"Bearer {aud_tok}", "X-Access-Purpose": purpose},
    )
    assert aud_case_sessions.status_code == 403
    assert aud_case_sessions.json()["error"]["code"] == "FORBIDDEN"

    with engine.connect() as conn:
        denied_rows = conn.execute(
            text(
                """
                SELECT action, user_id, username, role, case_id
                FROM audit_log
                WHERE action = 'access.denied' AND user_id = :uid
                ORDER BY seq DESC LIMIT 2
                """
            ),
            {"uid": users["auditor"]["id"]},
        ).mappings().fetchall()
    assert len(denied_rows) >= 2
    assert all(r["case_id"] == case_id for r in denied_rows)
    assert all(r["role"] == "auditor" for r in denied_rows)

    # 5. Admin without explicit grant GET case -> 403
    adm_case = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {adm_tok}", "X-Access-Purpose": purpose},
    )
    assert adm_case.status_code == 403
    assert adm_case.json()["error"]["code"] == "FORBIDDEN"

    # 6. Admin without explicit grant GET session -> 403
    adm_session = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {adm_tok}", "X-Access-Purpose": purpose},
    )
    assert adm_session.status_code == 403
    assert adm_session.json()["error"]["code"] == "FORBIDDEN"


def test_tb4_4_access_revocation(temp_db, client):
    """
    TB4.4: Revoking access via supervisor DELETE /cases/{id}/access/{user_id}
    denies the next request immediately (returns 403 FORBIDDEN).
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    sup_tok = get_token(users, "supervisor")
    inv_tok = get_token(users, "investigator")
    inv_id = users["investigator"]["id"]
    purpose = "TB4.4 access revocation test"

    # Supervisor creates case and grants investigator access
    c_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-REVOKE-1", "title": "Revocation Test Case"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    case_id = c_res.json()["id"]

    client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": inv_id, "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )

    # Investigator creates witness & session successfully
    w_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"preferred_language": "en"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert w_res.status_code == 201
    wid = w_res.json()["id"]

    s_res = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert s_res.status_code == 201
    sid = s_res.json()["id"]

    # Verify investigator can view session
    res_before = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_before.status_code == 200

    # Supervisor revokes investigator access
    res_revoke = client.delete(
        f"/api/v1/cases/{case_id}/access/{inv_id}",
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert res_revoke.status_code == 200
    assert res_revoke.json()["status"] == "revoked"

    # Investigator subsequent access to case -> 403 FORBIDDEN
    res_case_denied = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_case_denied.status_code == 403
    assert res_case_denied.json()["error"]["code"] == "FORBIDDEN"

    # Investigator subsequent access to session -> 403 FORBIDDEN
    res_session_denied = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert res_session_denied.status_code == 403
    assert res_session_denied.json()["error"]["code"] == "FORBIDDEN"

    # Verify access.denied audit entries were created
    with engine.connect() as conn:
        denied_count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM audit_log
                WHERE action = 'access.denied' AND user_id = :uid AND case_id = :cid
                """
            ),
            {"uid": inv_id, "cid": case_id},
        ).scalar()
    assert denied_count >= 2


def test_tb4_5_purpose_header_and_session_complete(temp_db, client):
    """
    TB4.5:
    - Omission of X-Access-Purpose or value < 5 chars returns 400 PURPOSE_REQUIRED.
    - POST /sessions/{sid}/complete transitions session status to completed and audits session.complete.
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    sup_tok = get_token(users, "supervisor")
    purpose = "TB4.5 purpose header verification and session completion"

    c_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-PURPOSE-01", "title": "Purpose Testing Case"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    case_id = c_res.json()["id"]

    # 1. Missing purpose header on case GET -> 400
    res_no_purpose = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert res_no_purpose.status_code == 400
    assert res_no_purpose.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 2. Too short purpose header (< 5 chars) -> 400
    res_short_purpose = client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": "abc"},
    )
    assert res_short_purpose.status_code == 400
    assert res_short_purpose.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # Create witness and session with valid purpose
    w_res = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"preferred_language": "en"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    wid = w_res.json()["id"]

    s_res = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    sid = s_res.json()["id"]

    # 3. Missing purpose header on session GET -> 400
    res_s_no_purpose = client.get(
        f"/api/v1/sessions/{sid}",
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert res_s_no_purpose.status_code == 400
    assert res_s_no_purpose.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 4. Complete session
    res_complete = client.post(
        f"/api/v1/sessions/{sid}/complete",
        json={"final_image_id": None},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert res_complete.status_code == 200
    assert res_complete.json()["status"] == "completed"

    # Verify session status in DB
    with engine.connect() as conn:
        s_row = conn.execute(
            text("SELECT status, completed_at FROM sessions WHERE id = :sid"),
            {"sid": sid},
        ).mappings().fetchone()
    assert s_row["status"] == "completed"
    assert s_row["completed_at"] is not None

    # Verify session.complete audit log entry
    with engine.connect() as conn:
        audit_row = conn.execute(
            text("SELECT action, resource_id, case_id FROM audit_log WHERE action = 'session.complete' AND resource_id = :sid"),
            {"sid": sid},
        ).mappings().fetchone()
    assert audit_row is not None
    assert audit_row["case_id"] == case_id


def test_case_list_role_filtering(temp_db, client):
    """
    Test role-based case listing:
    - Supervisor and auditor see all cases.
    - Investigator sees only cases with active case_access grants.
    """
    users = temp_db["users"]
    sup_tok = get_token(users, "supervisor")
    inv_tok = get_token(users, "investigator")
    aud_tok = get_token(users, "auditor")
    inv_id = users["investigator"]["id"]
    purpose = "Testing case list role filtering"

    # Supervisor creates 2 cases
    c1 = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-LIST-1", "title": "Case One", "station": "Station Alpha", "offence_summary": "Summary 1"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    ).json()["id"]

    client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-LIST-2", "title": "Case Two", "station": "Station Beta", "offence_summary": "Summary 2"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )

    # Supervisor grants investigator access to Case One only
    client.post(
        f"/api/v1/cases/{c1}/access",
        json={"user_id": inv_id, "access_level": "view"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )

    # Investigator lists cases -> only Case One returned, includes station
    inv_list = client.get("/api/v1/cases", headers={"Authorization": f"Bearer {inv_tok}"}).json()
    assert len(inv_list) == 1
    assert inv_list[0]["id"] == c1
    assert inv_list[0]["station"] == "Station Alpha"

    # Supervisor lists cases -> both cases returned with station
    sup_list = client.get("/api/v1/cases", headers={"Authorization": f"Bearer {sup_tok}"}).json()
    assert len(sup_list) == 2
    stations = {c["station"] for c in sup_list}
    assert stations == {"Station Alpha", "Station Beta"}

    # Auditor lists cases -> both cases returned, but station and offence_summary are strictly omitted (§6.3)
    aud_list = client.get("/api/v1/cases", headers={"Authorization": f"Bearer {aud_tok}"}).json()
    assert len(aud_list) == 2
    for case_item in aud_list:
        assert "station" not in case_item or case_item["station"] is None
        assert "offence_summary" not in case_item or case_item["offence_summary"] is None
        assert "id" in case_item
        assert "case_number" in case_item
        assert "title" in case_item
        assert "status" in case_item


def test_tb4_6_atomic_mutation_rollback_on_audit_failure(temp_db, client):
    """
    FIX 3: Verify that when write_audit_entry fails, the business mutation
    is completely rolled back and neither the business record nor a partial audit
    entry is committed.
    """
    users = temp_db["users"]
    db_path = temp_db["path"]
    engine = temp_db["engine"]
    sup_tok = get_token(users, "supervisor")

    # 1. Install a temporary trigger that aborts audit_log write on case.create
    con = sqlite3.connect(str(db_path))
    con.execute(
        """
        CREATE TRIGGER test_fail_case_audit BEFORE INSERT ON audit_log
        WHEN NEW.action = 'case.create'
        BEGIN
            SELECT RAISE(ABORT, 'Simulated failure during audit log write');
        END;
        """
    )
    con.commit()
    con.close()

    # 2. Attempt case creation -> must fail
    with pytest.raises((sqlite3.DatabaseError, DBAPIError)):
        client.post(
            "/api/v1/cases",
            json={"case_number": "FIR-ATOMIC-FAIL-1", "title": "Atomic Rollback Test Case"},
            headers={"Authorization": f"Bearer {sup_tok}"},
        )

    # 3. Verify database state: FIR-ATOMIC-FAIL-1 was NOT committed to cases table
    with engine.connect() as conn:
        case_row = conn.execute(
            text("SELECT id FROM cases WHERE case_number = 'FIR-ATOMIC-FAIL-1'")
        ).fetchone()
        assert case_row is None, "Business mutation succeeded despite audit failure!"

        # Verify no audit_log entry was created
        audit_count = conn.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE action = 'case.create'")
        ).scalar()
        assert audit_count == 0

    # 4. Remove the failure trigger
    con = sqlite3.connect(str(db_path))
    con.execute("DROP TRIGGER IF EXISTS test_fail_case_audit;")
    con.commit()
    con.close()

    # 5. Subsequent case creation succeeds cleanly and contiguous seq is allocated
    res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-ATOMIC-FAIL-1", "title": "Atomic Rollback Test Case"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    assert res.status_code == 201
    created_case_id = res.json()["id"]

    with engine.connect() as conn:
        committed_case = conn.execute(
            text("SELECT id, case_number FROM cases WHERE id = :id"),
            {"id": created_case_id},
        ).fetchone()
        assert committed_case is not None

        audit_entry = conn.execute(
            text("SELECT seq, action, resource_id, entry_hash FROM audit_log WHERE action = 'case.create'")
        ).mappings().fetchone()
        assert audit_entry is not None
        assert audit_entry["resource_id"] == created_case_id
        assert audit_entry["seq"] == 1


def test_tb4_7_auditor_session_enumeration_denied(temp_db, client):
    """
    FIX 2: Verify that GET /cases/{case_id}/sessions denies auditors with 403,
    writes access.denied audit record, denies users without access, and allows supervisors.
    """
    users = temp_db["users"]
    engine = temp_db["engine"]
    sup_tok = get_token(users, "supervisor")
    aud_tok = get_token(users, "auditor")
    inv_tok = get_token(users, "investigator")
    inv_id = users["investigator"]["id"]
    purpose = "Auditor session enumeration verification"

    # Create case, witness, session
    c_res = client.post(
        "/api/v1/cases",
        json={"case_number": "FIR-AUD-ENUM-1", "title": "Auditor Enum Test"},
        headers={"Authorization": f"Bearer {sup_tok}"},
    )
    cid = c_res.json()["id"]

    w_res = client.post(
        f"/api/v1/cases/{cid}/witnesses",
        json={"preferred_language": "en"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    wid = w_res.json()["id"]

    s_res = client.post(
        f"/api/v1/cases/{cid}/sessions",
        json={"witness_id": wid, "kind": "face"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert s_res.status_code == 201

    # 1. Auditor attempts to enumerate sessions -> 403 FORBIDDEN
    aud_res = client.get(
        f"/api/v1/cases/{cid}/sessions",
        headers={"Authorization": f"Bearer {aud_tok}", "X-Access-Purpose": purpose},
    )
    assert aud_res.status_code == 403
    assert aud_res.json()["error"]["code"] == "FORBIDDEN"

    with engine.connect() as conn:
        denied = conn.execute(
            text("SELECT action, role, case_id FROM audit_log WHERE action = 'access.denied' AND user_id = :uid"),
            {"uid": users["auditor"]["id"]},
        ).mappings().fetchone()
        assert denied is not None
        assert denied["case_id"] == cid
        assert denied["role"] == "auditor"

    # 2. Investigator without grant attempts to enumerate sessions -> 403 FORBIDDEN
    inv_no_grant = client.get(
        f"/api/v1/cases/{cid}/sessions",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert inv_no_grant.status_code == 403

    # 3. Supervisor lists sessions -> 200 OK
    sup_sessions = client.get(
        f"/api/v1/cases/{cid}/sessions",
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    assert sup_sessions.status_code == 200
    assert len(sup_sessions.json()) == 1
    assert sup_sessions.json()[0]["case_id"] == cid

    # 4. Grant investigator access -> 200 OK
    client.post(
        f"/api/v1/cases/{cid}/access",
        json={"user_id": inv_id, "access_level": "view"},
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    inv_with_grant = client.get(
        f"/api/v1/cases/{cid}/sessions",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert inv_with_grant.status_code == 200

    # 5. Revoke investigator access -> 403 FORBIDDEN
    client.delete(
        f"/api/v1/cases/{cid}/access/{inv_id}",
        headers={"Authorization": f"Bearer {sup_tok}", "X-Access-Purpose": purpose},
    )
    inv_revoked = client.get(
        f"/api/v1/cases/{cid}/sessions",
        headers={"Authorization": f"Bearer {inv_tok}", "X-Access-Purpose": purpose},
    )
    assert inv_revoked.status_code == 403
