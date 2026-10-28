"""
Unit tests for Milestone A7: Forensic transforms (age, disguise, profile).
Covers:
- ForensicTransformEngine prompt construction, speculative tagging, and disguise targeting
- Service-key authentication enforcement on POST /ml/v1/transform
- Request schema validation
- Mocked transformation execution for age, disguise removal, and lateral profile
"""

import base64
import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from PIL import Image

from ml_service.app.core.config import settings
from ml_service.app.main import app
from ml_service.app.models.manager import model_manager
from ml_service.app.transforms.forensic_transforms import (
    SUPPORTED_TRANSFORM_KINDS,
    transform_engine,
)

client = TestClient(app)


def create_dummy_png_base64(width: int = 64, height: int = 64, color: str = "gray") -> str:
    """Helper to generate a small base64 data URI for test payloads."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ============================================================================
# 1. ForensicTransformEngine Unit Tests
# ============================================================================
def test_transform_engine_supported_kinds():
    """Verify all 4 required forensic transform types are supported."""
    kinds = transform_engine.get_supported_transforms()
    assert len(kinds) == 4
    for k in ("age_progression", "age_regression", "disguise_removal", "side_profile"):
        assert k in kinds


def test_transform_engine_age_progression_prompt():
    """Verify age progression prompt construction and speculative flag."""
    prompt, region, spec = transform_engine.build_transform_prompt("age_progression", age_delta_years=25)
    assert "25 years older" in prompt
    assert spec is True
    assert region == "cheeks"


def test_transform_engine_disguise_removal_prompt():
    """Verify disguise removal targeting glasses and speculative flag."""
    prompt, region, spec = transform_engine.build_transform_prompt("disguise_removal", target_disguise="glasses")
    assert "without eyeglasses" in prompt
    assert spec is True
    assert region == "eyes"


def test_transform_engine_side_profile_prompt():
    """Verify side profile lateral perspective prompt and speculative flag."""
    prompt, region, spec = transform_engine.build_transform_prompt("side_profile")
    assert "lateral side profile" in prompt
    assert spec is True


def test_transform_engine_unsupported_kind_raises():
    """Verify ValueError on invalid transform kind."""
    with pytest.raises(ValueError):
        transform_engine.build_transform_prompt("invalid_transform_kind")


# ============================================================================
# 2. POST /ml/v1/transform Endpoint Tests
# ============================================================================
def test_transform_auth_missing_header():
    """Verify 401 when X-Service-Key is omitted."""
    payload = {
        "image_b64": create_dummy_png_base64(),
        "transform_kind": "age_progression",
    }
    response = client.post("/ml/v1/transform", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_transform_validation_missing_image():
    """Verify 422 when image is missing."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {"transform_kind": "age_progression"}
    response = client.post("/ml/v1/transform", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_transform_validation_invalid_kind():
    """Verify 422 when transform_kind is unknown."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "transform_kind": "unknown_transform",
    }
    response = client.post("/ml/v1/transform", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_transform_execution_age_progression(monkeypatch):
    """Verify successful age progression transform execution."""
    mock_pipe = MagicMock()
    mock_synth = Image.new("RGB", (64, 64), color="orange")
    mock_pipe.return_value = MagicMock(images=[mock_synth])
    monkeypatch.setattr(model_manager, "load_pipeline", lambda **kwargs: mock_pipe)

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(64, 64, "gray"),
        "transform_kind": "age_progression",
        "age_delta_years": 20,
        "seed": 42,
    }

    response = client.post("/ml/v1/transform", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["transform_kind"] == "age_progression"
    assert data["schema_kind"] == "age"
    assert data["speculative"] is True
    assert "data:image/png;base64," in data["image_base64"]


def test_transform_execution_side_profile(monkeypatch):
    """Verify successful side profile transform execution."""
    mock_pipe = MagicMock()
    mock_synth = Image.new("RGB", (64, 64), color="purple")
    mock_pipe.return_value = MagicMock(images=[mock_synth])
    monkeypatch.setattr(model_manager, "load_pipeline", lambda **kwargs: mock_pipe)

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(64, 64, "gray"),
        "transform_kind": "side_profile",
        "seed": 777,
    }

    response = client.post("/ml/v1/transform", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["transform_kind"] == "side_profile"
    assert data["schema_kind"] == "profile"
    assert data["speculative"] is True
