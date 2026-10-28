import io
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

import numpy as np
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
from backend.app.services.gallery_service import GalleryIndex, gallery_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


def make_embedding(seed: int) -> list[float]:
    rng = np.random.RandomState(seed)
    vec = rng.randn(512).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / norm).tolist()


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

    # Set storage dir in tmp
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    settings.STORAGE_DIR = str(storage_dir)

    # Reset gallery index
    gallery_index.reset()

    yield {
        "engine": engine,
        "users": users,
        "path": db_path,
        "storage": storage_dir,
    }

    engine.dispose()
    set_engine(None)
    gallery_index.reset()
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


def _setup_case_and_session(client, token: str, users: dict, session_kind: str = "face") -> tuple[str, str]:
    sup_token = _token(users, "supervisor")
    purpose = "setup-test-case-and-session"

    # Create case
    case_resp = client.post(
        "/api/v1/cases",
        json={"case_number": f"CASE-{uuid.uuid4().hex[:6].upper()}", "title": "Suspect Investigation"},
        headers={"Authorization": f"Bearer {token}", "X-Access-Purpose": purpose},
    )
    assert case_resp.status_code == 201, case_resp.text
    case_id = case_resp.json()["id"]

    # Grant investigator edit access
    client.post(
        f"/api/v1/cases/{case_id}/access",
        json={"user_id": users["investigator"]["id"], "access_level": "edit"},
        headers={"Authorization": f"Bearer {sup_token}", "X-Access-Purpose": purpose},
    )

    # Create witness
    wit_resp = client.post(
        f"/api/v1/cases/{case_id}/witnesses",
        json={"alias": "Witness 1", "preferred_language": "en"},
        headers={"Authorization": f"Bearer {token}", "X-Access-Purpose": purpose},
    )
    assert wit_resp.status_code == 201, wit_resp.text
    wit_id = wit_resp.json()["id"]

    # Create session
    sess_resp = client.post(
        f"/api/v1/cases/{case_id}/sessions",
        json={"witness_id": wit_id, "kind": session_kind},
        headers={"Authorization": f"Bearer {token}", "X-Access-Purpose": purpose},
    )
    assert sess_resp.status_code == 201, sess_resp.text
    sess_id = sess_resp.json()["id"]
    return case_id, sess_id


# ==============================================================================
# TB11.2: Gallery upload permissions, validation, and consent verification
# ==============================================================================
def test_tb11_2_gallery_upload_permissions_and_validation(client, temp_db):
    users = temp_db["users"]
    admin_token = _token(users, "admin")
    inv_token = _token(users, "investigator")
    sup_token = _token(users, "supervisor")

    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"

    # 1. Non-admin uploads must be rejected with 403 FORBIDDEN
    resp_inv = client.post(
        "/api/v1/gallery/faces",
        data={"label": "Suspect_A", "source": "synthetic"},
        files={"file": ("face.png", io.BytesIO(dummy_png), "image/png")},
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert resp_inv.status_code == 403
    assert resp_inv.json()["error"]["code"] == "FORBIDDEN"

    resp_sup = client.post(
        "/api/v1/gallery/faces",
        data={"label": "Suspect_A", "source": "synthetic"},
        files={"file": ("face.png", io.BytesIO(dummy_png), "image/png")},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert resp_sup.status_code == 403

    # 2. Consented-volunteer upload WITHOUT consent_ref must return 422 VALIDATION_ERROR
    resp_no_consent = client.post(
        "/api/v1/gallery/faces",
        data={"label": "Volunteer_1", "source": "consented_volunteer"},
        files={"file": ("volunteer.png", io.BytesIO(dummy_png), "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_no_consent.status_code == 422
    assert resp_no_consent.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Consented-volunteer upload with BLANK consent_ref must return 422 VALIDATION_ERROR
    resp_blank_consent = client.post(
        "/api/v1/gallery/faces",
        data={"label": "Volunteer_1", "source": "consented_volunteer", "consent_ref": "   "},
        files={"file": ("volunteer.png", io.BytesIO(dummy_png), "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_blank_consent.status_code == 422

    # 4. Invalid source value must return 422
    resp_invalid_source = client.post(
        "/api/v1/gallery/faces",
        data={"label": "Person_X", "source": "real_suspect"},
        files={"file": ("face.png", io.BytesIO(dummy_png), "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_invalid_source.status_code == 422

    # 5. Successful synthetic face upload (admin only)
    emb_1 = make_embedding(seed=42)
    with patch("backend.app.routers.gallery.ml_proxy.get_embedding", return_value=(emb_1, "face_embedder_v1")):
        resp_synth = client.post(
            "/api/v1/gallery/faces",
            data={"label": "Synthetic_Face_01", "source": "synthetic"},
            files={"file": ("synth_01.png", io.BytesIO(dummy_png), "image/png")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp_synth.status_code == 201, resp_synth.text
    synth_data = resp_synth.json()
    assert synth_data["label"] == "Synthetic_Face_01"
    assert synth_data["source"] == "synthetic"
    assert synth_data["consent_ref"] is None
    assert synth_data["embedding_model_version"] == "face_embedder_v1"
    assert "gallery/" in synth_data["image_path"]

    # 6. Successful consented volunteer face upload with consent_ref
    emb_2 = make_embedding(seed=43)
    with patch("backend.app.routers.gallery.ml_proxy.get_embedding", return_value=(emb_2, "face_embedder_v1")):
        resp_vol = client.post(
            "/api/v1/gallery/faces",
            data={
                "label": "Volunteer_Alice",
                "source": "consented_volunteer",
                "consent_ref": "CONSENT-2026-0042",
            },
            files={"file": ("vol_alice.png", io.BytesIO(dummy_png), "image/png")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp_vol.status_code == 201, resp_vol.text
    vol_data = resp_vol.json()
    assert vol_data["label"] == "Volunteer_Alice"
    assert vol_data["source"] == "consented_volunteer"
    assert vol_data["consent_ref"] == "CONSENT-2026-0042"

    # 7. Verify gallery listing
    resp_list = client.get("/api/v1/gallery", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_list.status_code == 200
    items = resp_list.json()
    assert len(items) == 2

    # 8. Verify audit logs for gallery.add
    engine = temp_db["engine"]
    with engine.connect() as conn:
        audit_rows = conn.execute(
            text("SELECT action, resource_id, status_code, details_json FROM audit_log WHERE action = 'gallery.add'")
        ).fetchall()
        assert len(audit_rows) == 2
        for row in audit_rows:
            assert row[0] == "gallery.add"
            assert row[2] == 201


# ==============================================================================
# TB11.3: Match API, cosine similarity rank, persistence, disclaimer, possible leads
# ==============================================================================
def test_tb11_3_match_search_results_and_disclaimer(client, temp_db):
    users = temp_db["users"]
    admin_token = _token(users, "admin")
    inv_token = _token(users, "investigator")
    engine = temp_db["engine"]

    # Create case and session
    case_id, session_id = _setup_case_and_session(client, inv_token, users)

    # Insert an image record and file on disk for the session
    storage_path = Path(settings.STORAGE_DIR)
    img_dir = storage_path / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    image_id = str(uuid.uuid4())
    img_file = img_dir / f"{image_id}.png"
    img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    img_file.write_bytes(img_bytes)

    round_id = str(uuid.uuid4())
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    """
                    INSERT INTO rounds (id, session_id, round_no, kind, status, created_at)
                    VALUES (:id, :session_id, 1, 'initial', 'done', '2026-10-28T12:00:00.000Z')
                    """
                ),
                {"id": round_id, "session_id": session_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO images (
                        id, session_id, round_id, variant_index, kind, width, height,
                        prompt_text, sha256, storage_path, model_versions_json, created_at
                    ) VALUES (
                        :id, :session_id, :round_id, 0, 'variant', 512, 512,
                        'suspect face', 'dummy_sha', :storage_path, '{}', '2026-10-28T12:00:00.000Z'
                    )
                    """
                ),
                {
                    "id": image_id,
                    "session_id": session_id,
                    "round_id": round_id,
                    "storage_path": f"images/{image_id}.png",
                },
            )

    # Seed 3 gallery faces:
    # Face A: seed=100 (will match query embedding perfectly)
    # Face B: seed=200
    # Face C: seed=300
    emb_a = make_embedding(seed=100)
    emb_b = make_embedding(seed=200)
    emb_c = make_embedding(seed=300)

    for label, emb in [("Face_A", emb_a), ("Face_B", emb_b), ("Face_C", emb_c)]:
        with patch("backend.app.routers.gallery.ml_proxy.get_embedding", return_value=(emb, "v1")):
            r = client.post(
                "/api/v1/gallery/faces",
                data={"label": label, "source": "synthetic"},
                files={"file": (f"{label}.png", io.BytesIO(img_bytes), "image/png")},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r.status_code == 201

    # Now execute match search using investigator token
    # Query embedding is identical to Face A
    with patch("backend.app.routers.match.ml_proxy.get_embedding", return_value=(emb_a, "v1")):
        match_resp = client.post(
            "/api/v1/match/search",
            json={
                "session_id": session_id,
                "image_id": image_id,
                "top_k": 3,
            },
            headers={
                "Authorization": f"Bearer {inv_token}",
                "X-Access-Purpose": "match-suspect-against-gallery",
            },
        )

    assert match_resp.status_code == 200, match_resp.text
    data = match_resp.json()

    # Invariants verification
    # 1. Disclaimer text exact match
    expected_disclaimer = "AI-generated investigative aid — not a photograph, not evidence of identity."
    assert data["disclaimer"] == expected_disclaimer

    # 2. Response message uses "possible leads", never "identified"
    assert "possible leads" in data["message"].lower()
    assert "identified" not in data["message"].lower()

    # 3. Check rank order and cosine similarity
    results = data["results"]
    assert len(results) == 3
    # Top rank should be Face_A with similarity near 1.0
    assert results[0]["label"] == "Face_A"
    assert results[0]["rank"] == 1
    assert pytest.approx(results[0]["similarity"], 0.001) == 1.0
    assert results[1]["rank"] == 2
    assert results[2]["rank"] == 3
    assert results[0]["similarity"] >= results[1]["similarity"] >= results[2]["similarity"]

    # 4. Check database persistence in match_searches and match_results
    search_id = data["search_id"]
    with engine.connect() as conn:
        s_row = conn.execute(
            text("SELECT id, session_id, image_id, top_k FROM match_searches WHERE id = :id"),
            {"id": search_id},
        ).fetchone()
        assert s_row is not None
        assert s_row[1] == session_id
        assert s_row[2] == image_id

        r_rows = conn.execute(
            text("SELECT rank, similarity, gallery_face_id FROM match_results WHERE search_id = :sid ORDER BY rank ASC"),
            {"sid": search_id},
        ).fetchall()
        assert len(r_rows) == 3
        assert r_rows[0][0] == 1
        assert pytest.approx(r_rows[0][1], 0.001) == 1.0

        # 5. Check audit entry
        audit_match = conn.execute(
            text("SELECT action, resource_type, resource_id, purpose, status_code FROM audit_log WHERE action = 'match.search'")
        ).fetchone()
        assert audit_match is not None
        assert audit_match[1] == "match_search"
        assert audit_match[2] == search_id
        assert audit_match[3] == "match-suspect-against-gallery"
        assert audit_match[4] == 200


# ==============================================================================
# TB11.4: Cross-session consensus calculation fixture (§8.6)
# ==============================================================================
def test_tb11_4_consensus_fixture_calculation(client, temp_db):
    users = temp_db["users"]
    inv_token = _token(users, "investigator")
    engine = temp_db["engine"]

    # 1. Setup primary case
    case_resp = client.post(
        "/api/v1/cases",
        json={"case_number": "CASE-CONSENSUS-01", "title": "Bank Heist"},
        headers={"Authorization": f"Bearer {inv_token}", "X-Access-Purpose": "test-consensus-setup"},
    )
    case_id = case_resp.json()["id"]

    # Setup second case to test cross-case exclusion
    case2_resp = client.post(
        "/api/v1/cases",
        json={"case_number": "CASE-OTHER-02", "title": "Other Case"},
        headers={"Authorization": f"Bearer {inv_token}", "X-Access-Purpose": "test-consensus-setup"},
    )
    case2_id = case2_resp.json()["id"]

    # Helper to add witness and session
    def add_session(cid: str, wit_name: str, attrs: dict) -> str:
        sup_token = _token(users, "supervisor")
        client.post(
            f"/api/v1/cases/{cid}/access",
            json={"user_id": users["investigator"]["id"], "access_level": "edit"},
            headers={"Authorization": f"Bearer {sup_token}", "X-Access-Purpose": "grant-access-for-test"},
        )
        w_resp = client.post(
            f"/api/v1/cases/{cid}/witnesses",
            json={"alias": wit_name, "preferred_language": "en"},
            headers={"Authorization": f"Bearer {inv_token}", "X-Access-Purpose": "setup-witness"},
        )
        assert w_resp.status_code == 201, w_resp.text
        wid = w_resp.json()["id"]
        s_resp = client.post(
            f"/api/v1/cases/{cid}/sessions",
            json={"witness_id": wid, "kind": "face"},
            headers={"Authorization": f"Bearer {inv_token}", "X-Access-Purpose": "setup-session"},
        )
        assert s_resp.status_code == 201, s_resp.text
        sid = s_resp.json()["id"]

        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(
                        """
                        INSERT INTO attribute_snapshots (
                            id, session_id, version, attributes_json, change_source, created_at
                        ) VALUES (
                            :id, :session_id, 1, :json_str, 'statement', '2026-10-28T12:00:00.000Z'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "session_id": sid,
                        "json_str": json.dumps({"schema_version": "1.0", "attributes": attrs}),
                    },
                )
        return sid

    # Session 1 in Case 1:
    s1_attrs = {
        "skin_tone": {"value": "wheatish", "source": "stated", "confidence": "sure"},
        "eye_color": {"value": "brown", "source": "stated", "confidence": "sure"},
        "face_shape": {"value": "oval", "source": "stated", "confidence": "sure"},
        "nose_shape": {"value": "straight", "source": "inferred", "confidence": "unsure"},  # inferred: must be skipped!
    }
    add_session(case_id, "Witness_1", s1_attrs)

    # Session 2 in Case 1:
    s2_attrs = {
        "skin_tone": {"value": "wheatish", "source": "stated", "confidence": "somewhat"},
        "eye_color": {"value": "black", "source": "user_edit", "confidence": "sure"},
        "face_shape": {"value": "oval", "source": "user_edit", "confidence": "sure"},
    }
    add_session(case_id, "Witness_2", s2_attrs)

    # Session 3 in Case 1:
    s3_attrs = {
        "skin_tone": {"value": "fair", "source": "user_edit", "confidence": "unsure"},
        "eye_color": {"value": "brown", "source": "stated", "confidence": "somewhat"},
        "face_shape": {"value": "oval", "source": "stated", "confidence": "sure"},
        "lip_thickness": {"value": "medium", "source": "stated", "confidence": "sure"},  # n=1: agreement should be null!
    }
    add_session(case_id, "Witness_3", s3_attrs)

    # Session 4 in Case 2 (Other case):
    s4_attrs = {
        "skin_tone": {"value": "dark", "source": "stated", "confidence": "sure"},
    }
    add_session(case2_id, "Witness_Other", s4_attrs)

    # Call consensus endpoint
    resp = client.post(
        f"/api/v1/cases/{case_id}/consensus",
        headers={
            "Authorization": f"Bearer {inv_token}",
            "X-Access-Purpose": "review-cross-witness-consensus",
        },
    )
    assert resp.status_code == 200, resp.text
    consensus = resp.json()

    assert consensus["case_id"] == case_id
    assert consensus["session_count"] == 3

    attrs = consensus["attributes"]

    # 1. skin_tone: 3 values (wheatish, wheatish, fair)
    # modal = wheatish (2), n = 3, agreement = 2/3 = 0.6667, disagreement = True
    st = attrs["skin_tone"]
    assert st["n"] == 3
    assert st["modal_value"] == "wheatish"
    assert pytest.approx(st["agreement"], 0.001) == 0.6667
    assert st["disagreement"] is True
    assert len(st["values"]) == 3
    vals = [v["value"] for v in st["values"]]
    assert "dark" not in vals  # ensure other case is excluded!

    # 2. eye_color: 3 values (brown, black, brown)
    # modal = brown (2), n = 3, agreement = 2/3 = 0.6667, disagreement = True
    ec = attrs["eye_color"]
    assert ec["n"] == 3
    assert ec["modal_value"] == "brown"
    assert pytest.approx(ec["agreement"], 0.001) == 0.6667
    assert ec["disagreement"] is True

    # 3. face_shape: 3 values (all oval)
    # modal = oval (3), n = 3, agreement = 1.0, disagreement = False
    fs = attrs["face_shape"]
    assert fs["n"] == 3
    assert fs["modal_value"] == "oval"
    assert fs["agreement"] == 1.0
    assert fs["disagreement"] is False

    # 4. nose_shape: was source='inferred' in session 1, should NOT appear in consensus!
    assert "nose_shape" not in attrs

    # 5. lip_thickness: only in session 3 (n = 1) -> agreement must be null per §8.6!
    lt = attrs["lip_thickness"]
    assert lt["n"] == 1
    assert lt["modal_value"] == "medium"
    assert lt["agreement"] is None
    assert lt["disagreement"] is False

    # 6. Disagreements list must contain skin_tone and eye_color, not face_shape
    disagreements = consensus["disagreements"]
    assert "skin_tone" in disagreements
    assert "eye_color" in disagreements
    assert "face_shape" not in disagreements

    # 7. Verify consensus.view audit entry
    with engine.connect() as conn:
        audit_row = conn.execute(
            text("SELECT action, resource_id, purpose, status_code FROM audit_log WHERE action = 'consensus.view'")
        ).fetchone()
        assert audit_row is not None
        assert audit_row[0] == "consensus.view"
        assert audit_row[1] == case_id
        assert audit_row[2] == "review-cross-witness-consensus"
        assert audit_row[3] == 200


# ==============================================================================
# Edge cases: Empty gallery, ML unavailable, Auditor RBAC, Malformed embeddings
# ==============================================================================
def test_edge_cases_gallery_and_match(client, temp_db):
    users = temp_db["users"]
    inv_token = _token(users, "investigator")
    auditor_token = _token(users, "auditor")
    engine = temp_db["engine"]

    case_id, session_id = _setup_case_and_session(client, inv_token, users)

    # 1. Auditor cannot access consensus (403 FORBIDDEN)
    resp_aud_cons = client.post(
        f"/api/v1/cases/{case_id}/consensus",
        headers={"Authorization": f"Bearer {auditor_token}", "X-Access-Purpose": "auditor-check"},
    )
    assert resp_aud_cons.status_code == 403
    assert resp_aud_cons.json()["error"]["code"] == "FORBIDDEN"

    # 2. Missing purpose on consensus returns 400 PURPOSE_REQUIRED
    resp_no_purp = client.post(
        f"/api/v1/cases/{case_id}/consensus",
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert resp_no_purp.status_code == 400
    assert resp_no_purp.json()["error"]["code"] == "PURPOSE_REQUIRED"

    # 3. Match search on empty gallery returns valid empty results without crashing
    storage_path = Path(settings.STORAGE_DIR)
    img_dir = storage_path / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_id = str(uuid.uuid4())
    img_file = img_dir / f"{img_id}.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    round_id = str(uuid.uuid4())
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    """
                    INSERT INTO rounds (id, session_id, round_no, kind, status, created_at)
                    VALUES (:id, :session_id, 1, 'initial', 'done', '2026-10-28T12:00:00.000Z')
                    """
                ),
                {"id": round_id, "session_id": session_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO images (
                        id, session_id, round_id, variant_index, kind, width, height,
                        prompt_text, sha256, storage_path, model_versions_json, created_at
                    ) VALUES (
                        :id, :session_id, :round_id, 0, 'variant', 512, 512,
                        'suspect', 'sha', :storage_path, '{}', '2026-10-28T12:00:00.000Z'
                    )
                    """
                ),
                {
                    "id": img_id,
                    "session_id": session_id,
                    "round_id": round_id,
                    "storage_path": f"images/{img_id}.png",
                },
            )

    dummy_emb = make_embedding(1)
    with patch("backend.app.routers.match.ml_proxy.get_embedding", return_value=(dummy_emb, "v1")):
        resp_empty = client.post(
            "/api/v1/match/search",
            json={"session_id": session_id, "image_id": img_id, "top_k": 5},
            headers={"Authorization": f"Bearer {inv_token}", "X-Access-Purpose": "empty-gallery-test"},
        )
    assert resp_empty.status_code == 200
    assert resp_empty.json()["results"] == []
    assert "Found 0 possible leads" in resp_empty.json()["message"]

    # 4. ML service unavailable returns 503 ML_UNAVAILABLE
    with patch(
        "backend.app.routers.match.ml_proxy.get_embedding",
        side_effect=AppError("ML_UNAVAILABLE", "ML proxy connection refused", status_code=503),
    ):
        resp_ml_down = client.post(
            "/api/v1/match/search",
            json={"session_id": session_id, "image_id": img_id, "top_k": 5},
            headers={"Authorization": f"Bearer {inv_token}", "X-Access-Purpose": "ml-down-test"},
        )
    assert resp_ml_down.status_code == 503
    assert resp_ml_down.json()["error"]["code"] == "ML_UNAVAILABLE"

    # 5. GalleryIndex safely rejects malformed embeddings in DB
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    """
                    INSERT INTO gallery_faces (
                        id, label, source, consent_ref, image_path,
                        embedding, embedding_model_version, added_by, added_at
                    ) VALUES (
                        :id, 'Corrupted', 'synthetic', NULL, 'gallery/corrupt.png',
                        :bad_blob, 'v1', :added_by, '2026-10-28T12:00:00.000Z'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "bad_blob": b"\x00\x01\x02\x03",  # 4 bytes instead of 2048!
                    "added_by": users["admin"]["id"],
                },
            )

    idx = GalleryIndex()
    idx.load_from_db(engine)
    assert len(idx) == 0  # malformed row was skipped safely without crashing


# ==============================================================================
# TB11.1: Live ML integration test (conditional)
# ==============================================================================
def test_tb11_1_live_ml_integration():
    """
    TB11.1 live check against live ML service and synthetic image set.
    Skipped if live ML service or synthetic dataset is not active on host.
    """
    import httpx

    ml_url = getattr(settings, "ML_SERVICE_URL", "http://localhost:8001")
    try:
        resp = httpx.get(f"{ml_url}/health", timeout=1.0)
        if resp.status_code != 200:
            pytest.skip(f"Live ML service at {ml_url} returned HTTP {resp.status_code}; skipping live check.")
    except Exception as exc:
        pytest.skip(f"Live ML service unreachable at {ml_url} ({exc}); skipping live check.")
