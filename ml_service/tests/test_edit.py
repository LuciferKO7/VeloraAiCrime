"""
Unit tests for Milestone A4: Region masks and /edit endpoint.
Covers:
- FacialRegionMasker 8-region anatomical geometry and feathering
- Mask combination logic
- Service-key authentication enforcement on POST /ml/v1/edit
- Input schema validation (missing images, invalid regions, missing instructions)
- Mocked inpainting composite execution and mask output verification
"""

import base64
import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from PIL import Image
import numpy as np

from ml_service.app.core.config import settings
from ml_service.app.main import app
from ml_service.app.masks.region_masker import CANONICAL_REGIONS, region_masker
from ml_service.app.models.manager import model_manager

client = TestClient(app)


def create_dummy_png_base64(width: int = 64, height: int = 64, color: str = "gray") -> str:
    """Helper to generate a small base64 data URI for test payloads."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ============================================================================
# 1. FacialRegionMasker Unit Tests
# ============================================================================
def test_region_masker_all_canonical_regions():
    """Verify that all 8 canonical anatomical regions generate valid, non-empty masks."""
    supported = region_masker.get_supported_regions()
    assert len(supported) == 8
    for reg in CANONICAL_REGIONS:
        assert reg in supported
        mask = region_masker.generate_region_mask(region=reg, image_size=(128, 128), feather_radius=4)
        assert mask.size == (128, 128)
        assert mask.mode == "L"
        arr = np.array(mask)
        assert np.max(arr) > 0, f"Mask for region {reg} is completely empty"


def test_region_masker_unsupported_region_raises():
    """Verify ValueError when requesting an invalid region."""
    with pytest.raises(ValueError) as exc_info:
        region_masker.generate_region_mask("unsupported_region_name")
    assert "Unsupported facial region" in str(exc_info.value)


def test_region_masker_feathering():
    """Verify that feathering produces smooth gradient edges rather than binary step edges."""
    mask_hard = region_masker.generate_region_mask("eyes", image_size=(128, 128), feather_radius=0)
    mask_feathered = region_masker.generate_region_mask("eyes", image_size=(128, 128), feather_radius=8)

    arr_hard = np.array(mask_hard)
    arr_feathered = np.array(mask_feathered)

    # In hard mask, pixels are strictly 0 or 255
    hard_unique = set(np.unique(arr_hard))
    assert hard_unique.issubset({0, 255})

    # In feathered mask, there exist intermediate gradient values
    feathered_intermediate = np.sum((arr_feathered > 0) & (arr_feathered < 255))
    assert feathered_intermediate > 0


def test_region_masker_combine_masks():
    """Verify combining multiple masks creates an anatomical union."""
    m_eyes = region_masker.generate_region_mask("eyes", image_size=(128, 128), feather_radius=0)
    m_mouth = region_masker.generate_region_mask("mouth", image_size=(128, 128), feather_radius=0)

    combined = region_masker.combine_masks([m_eyes, m_mouth], image_size=(128, 128))
    arr_c = np.array(combined)
    arr_e = np.array(m_eyes)
    arr_m = np.array(m_mouth)

    assert np.all(arr_c >= arr_e)
    assert np.all(arr_c >= arr_m)


# ============================================================================
# 2. POST /ml/v1/edit Endpoint Authentication & Validation Tests
# ============================================================================
def test_edit_auth_missing_header():
    """Verify 401 when X-Service-Key is omitted."""
    payload = {
        "image_b64": create_dummy_png_base64(),
        "region": "nose",
        "edit_instruction": "sharper nose bridge",
    }
    response = client.post("/ml/v1/edit", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_edit_auth_invalid_header():
    """Verify 401 when X-Service-Key is invalid."""
    headers = {"X-Service-Key": "wrong-key"}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "region": "nose",
        "edit_instruction": "sharper nose bridge",
    }
    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_edit_validation_missing_image():
    """Verify 422 when neither image_b64 nor image_id is provided."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "region": "nose",
        "edit_instruction": "sharper nose bridge",
    }
    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_edit_validation_missing_region_and_mask():
    """Verify 422 when neither region nor mask_b64 is provided."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "edit_instruction": "sharper nose bridge",
    }
    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_edit_validation_unsupported_region():
    """Verify 422 when an unsupported anatomical region is passed."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "region": "invalid_region_name",
        "edit_instruction": "sharper bridge",
    }
    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_edit_validation_missing_instructions():
    """Verify 422 when neither edit_instruction nor updated_attributes is supplied."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "region": "eyes",
    }
    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ============================================================================
# 3. POST /ml/v1/edit Execution Tests (Mocked Model)
# ============================================================================
def test_edit_execution_success_with_region(monkeypatch):
    """Verify successful localized edit execution with mock inpainting pipeline."""
    mock_pipe = MagicMock()
    mock_patch = Image.new("RGB", (64, 64), color="red")
    mock_pipe.return_value = MagicMock(images=[mock_patch])
    monkeypatch.setattr(model_manager, "load_pipeline", lambda **kwargs: mock_pipe)

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(64, 64, "blue"),
        "region": "mouth",
        "edit_instruction": "slightly fuller lips",
        "seed": 1234,
        "feather_radius": 4,
    }

    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["region"] == "mouth"
    assert data["seed_used"] == 1234
    assert "data:image/png;base64," in data["image_base64"]
    assert "data:image/png;base64," in data["mask_used_base64"]
    assert "forensic facial modification of mouth" in data["prompt_used"]


def test_edit_execution_with_custom_mask(monkeypatch):
    """Verify successful edit execution with a custom base64 mask."""
    mock_pipe = MagicMock()
    mock_patch = Image.new("RGB", (64, 64), color="yellow")
    mock_pipe.return_value = MagicMock(images=[mock_patch])
    monkeypatch.setattr(model_manager, "load_pipeline", lambda **kwargs: mock_pipe)

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(64, 64, "green"),
        "mask_b64": create_dummy_png_base64(64, 64, "white"),
        "edit_instruction": "add scar on left cheek",
        "seed": 5678,
    }

    response = client.post("/ml/v1/edit", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["seed_used"] == 5678
    assert "data:image/png;base64," in data["image_base64"]
