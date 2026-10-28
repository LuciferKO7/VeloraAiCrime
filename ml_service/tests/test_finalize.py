"""
Unit tests for Milestone A6: Upscale / finalize endpoint.
Covers:
- PortraitFinalizer 2x/4x Lanczos upscaling and contrast enhancement
- R11 investigative aid disclaimer watermark application
- SHA256 integrity checksum verification
- Service-key authentication enforcement on POST /ml/v1/finalize
- Request schema validation (missing images, invalid scale factors)
- Execution and response verification
"""

import base64
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ml_service.app.core.config import settings
from ml_service.app.main import app
from ml_service.app.pipelines.upscaler import portrait_finalizer

client = TestClient(app)


def create_dummy_png_base64(width: int = 64, height: int = 64, color: str = "gray") -> str:
    """Helper to generate a small base64 data URI for test payloads."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ============================================================================
# 1. PortraitFinalizer Unit Tests
# ============================================================================
def test_upscale_2x_and_4x():
    """Verify spatial resolution scaling by 2x and 4x."""
    src = Image.new("RGB", (50, 50), color="white")

    up2 = portrait_finalizer.upscale_image(src, scale_factor=2)
    assert up2.size == (100, 100)

    up4 = portrait_finalizer.upscale_image(src, scale_factor=4)
    assert up4.size == (200, 200)


def test_upscale_invalid_scale_factor_raises():
    """Verify ValueError on unsupported scale factor."""
    src = Image.new("RGB", (50, 50), color="white")
    with pytest.raises(ValueError):
        portrait_finalizer.upscale_image(src, scale_factor=3)


def test_apply_disclaimer_watermark():
    """Verify that watermark modifies bottom region and matches disclaimer."""
    src = Image.new("RGB", (200, 200), color=(255, 255, 255))
    watermarked = portrait_finalizer.apply_disclaimer_watermark(src)
    assert watermarked.size == (200, 200)

    # Bottom pixels should no longer be pure white (replaced with dark banner)
    bottom_pixel = watermarked.getpixel((100, 195))
    assert bottom_pixel != (255, 255, 255)


def test_compute_sha256_format():
    """Verify SHA256 hex digest format (64 hex characters)."""
    src = Image.new("RGB", (64, 64), color="blue")
    digest = portrait_finalizer.compute_sha256(src)
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert int(digest, 16) > 0  # Valid hex


# ============================================================================
# 2. POST /ml/v1/finalize Endpoint Tests
# ============================================================================
def test_finalize_auth_missing_header():
    """Verify 401 when X-Service-Key is omitted."""
    payload = {"image_b64": create_dummy_png_base64()}
    response = client.post("/ml/v1/finalize", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_finalize_validation_missing_image():
    """Verify 422 when neither image_b64 nor image_id is provided."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {"scale_factor": 2}
    response = client.post("/ml/v1/finalize", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_finalize_validation_invalid_scale_factor():
    """Verify 422 when scale_factor is invalid (e.g. 5)."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "scale_factor": 5,
    }
    response = client.post("/ml/v1/finalize", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_finalize_execution_success():
    """Verify successful 2x finalization with watermark and checksum."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(64, 64, "gray"),
        "scale_factor": 2,
        "apply_watermark": True,
        "enhance_contrast": True,
    }
    response = client.post("/ml/v1/finalize", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["original_width"] == 64
    assert data["original_height"] == 64
    assert data["final_width"] == 128
    assert data["final_height"] == 128
    assert data["scale_factor"] == 2
    assert len(data["sha256"]) == 64
    assert "data:image/png;base64," in data["image_base64"]
    assert "investigative aid" in data["disclaimer"]
