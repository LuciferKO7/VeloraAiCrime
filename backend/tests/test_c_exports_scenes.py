import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_exports_endpoint_purpose_enforced(client):
    """Confirm export endpoint requires X-Access-Purpose header >= 5 characters."""
    # Missing header
    res = client.post("/api/v1/cases/case-test-01/export", json={"session_id": "ses-01", "format": "pdf"})
    assert res.status_code == 400

    # Too short header
    res = client.post(
        "/api/v1/cases/case-test-01/export",
        json={"session_id": "ses-01", "format": "pdf"},
        headers={"X-Access-Purpose": "abc"}
    )
    assert res.status_code == 400

def test_exports_pdf_generation_and_download(client):
    """Test generating a court packet export and downloading authentic binary PDF 1.4 bytes."""
    payload = {
        "session_id": "ses-court-01",
        "format": "pdf",
        "language": "en",
        "attributes": {"face_shape": "oval", "jawline": "sharp"},
        "ai_assumed": [{"key": "eye_color", "note": "Varied across variants"}],
        "model_versions": {"image_gen": "realistic-vision-v5.1"}
    }
    res = client.post(
        "/api/v1/cases/case-test-01/export",
        json=payload,
        headers={"X-Access-Purpose": "Court packet compilation"}
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "sha256" in data
    assert len(data["sha256"]) == 64
    assert "download_url" in data
    export_id = data["id"]

    # Download binary PDF
    dl_res = client.get(f"/api/v1/exports/{export_id}/download")
    assert dl_res.status_code == 200
    assert dl_res.headers.get("content-type") == "application/pdf"
    content = dl_res.content
    assert content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in content

def test_scenes_endpoints_purpose_enforced(client):
    """Confirm scene endpoint requires valid X-Access-Purpose."""
    res = client.get("/api/v1/sessions/ses-01/scene")
    assert res.status_code == 400

    res = client.get("/api/v1/sessions/ses-01/scene", headers={"X-Access-Purpose": "Scene layout review"})
    assert res.status_code == 200
    scene_data = res.json()
    assert scene_data["session_id"] == "ses-01"
    assert "scene" in scene_data
    assert "entities" in scene_data["scene"]
