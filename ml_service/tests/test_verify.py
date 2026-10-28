"""
Comprehensive unit and integration test suite for Milestone A3: Embedder and Verifier.
Covers:
- Service-key authentication enforcement on /ml/v1/verify-attributes and /ml/v1/embed
- Request schema validation (empty attributes, missing image inputs, malformed base64)
- Exact arithmetic validation of attr_adherence and safe empty stated-attribute handling
- ArcFace model-unavailable 503 error enforcement when unapproved weights are unloaded
- Backward-compatibility of GeneratedImageItem with optional attr_adherence
- Unit tests with mock CLIP and real-model CLIP inference test on CPU (TA3.3/TA3.4)
"""

import base64
import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image
import torch

from ml_service.app.core.config import settings
from ml_service.app.main import app
from ml_service.app.pipelines.attribute_verifier import (
    ATTRIBUTE_ENUM_REGISTRY,
    build_candidate_prompt,
    CLIPAttributeVerifier,
)
from ml_service.app.routers.generate import GeneratedImageItem

client = TestClient(app)


def create_dummy_png_base64(width: int = 128, height: int = 128, color: str = "white") -> str:
    """Helper creating a valid base64 PNG data URI."""
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=color)
    img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


# ============================================================================
# 1. Authentication Tests
# ============================================================================
def test_verify_attributes_auth_missing_header():
    """Verify POST /ml/v1/verify-attributes rejects requests without X-Service-Key."""
    payload = {
        "image_b64": create_dummy_png_base64(),
        "requested_attributes": ["hair_length"],
    }
    response = client.post("/ml/v1/verify-attributes", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_verify_attributes_auth_invalid_header():
    """Verify POST /ml/v1/verify-attributes rejects requests with wrong service key."""
    headers = {"X-Service-Key": "wrong-key"}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "requested_attributes": ["hair_length"],
    }
    response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_embed_auth_missing_header():
    """Verify POST /ml/v1/embed rejects requests without X-Service-Key."""
    payload = {"image_b64": create_dummy_png_base64()}
    response = client.post("/ml/v1/embed", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_embed_auth_invalid_header():
    """Verify POST /ml/v1/embed rejects requests with wrong service key."""
    headers = {"X-Service-Key": "wrong-key"}
    payload = {"image_b64": create_dummy_png_base64()}
    response = client.post("/ml/v1/embed", json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


# ============================================================================
# 2. Schema Validation & Error Handling Tests
# ============================================================================
def test_verify_attributes_schema_missing_attributes():
    """Verify 422 when requested_attributes is empty."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": create_dummy_png_base64(),
        "requested_attributes": [],  # Empty violates min_length=1
    }
    response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_verify_attributes_invalid_image_base64():
    """Verify 422 when image_b64 is not a valid base64 image."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": "not_valid_base64_data",
        "requested_attributes": ["hair_length"],
    }
    response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Invalid base64" in response.json()["error"]["message"]


def test_embed_schema_missing_both_sources():
    """Verify 422 when neither image_b64 nor image_id is provided."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {}
    response = client.post("/ml/v1/embed", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_verify_attributes_schema_missing_both_sources():
    """Verify 422 when neither image_b64 nor image_id is provided to /verify-attributes."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {"requested_attributes": ["hair_length"]}
    response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_verify_image_id_not_found():
    """Verify 404 NOT_FOUND when image_id does not exist in local storage."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_id": "nonexistent-image-uuid-1234",
        "requested_attributes": ["hair_length"],
    }
    response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_verify_image_id_success_from_storage(monkeypatch):
    """Verify image_id is resolved and read from local storage according to contract."""
    settings.ML_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    temp_img_path = settings.ML_STORAGE_DIR / "test-storage-img-123.png"
    img = Image.new("RGB", (64, 64), color="blue")
    img.save(temp_img_path)

    # Mock attribute_verifier on router to return mock scores
    monkeypatch.setattr(
        "ml_service.app.routers.verify.attribute_verifier.verify_attributes",
        lambda image, requested_attributes, stated_attributes: {
            "attribute_scores": {"hair_length": {"bald": 0.9, "long": 0.1}},
            "stated_probabilities": {"hair_length": 0.9},
            "attr_adherence": 0.9,
        },
    )

    try:
        headers = {"X-Service-Key": settings.SERVICE_KEY}
        payload = {
            "image_id": "test-storage-img-123",
            "requested_attributes": ["hair_length"],
            "stated_attributes": {"hair_length": "bald"},
        }
        response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["image_id"] == "test-storage-img-123"
        assert data["attr_adherence"] == 0.9
    finally:
        if temp_img_path.exists():
            temp_img_path.unlink()


# ============================================================================
# 3. Model Safety & ArcFace Unloaded Gate Tests
# ============================================================================
def test_embed_model_unavailable_when_unloaded():
    """
    Verify POST /ml/v1/embed returns explicit 503 ML_UNAVAILABLE when
    ArcFace weights are not loaded, confirming zero fake embeddings are generated.
    """
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {"image_b64": create_dummy_png_base64()}
    response = client.post("/ml/v1/embed", json=payload, headers=headers)
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "ML_UNAVAILABLE"
    assert "ArcFace model weights" in data["error"]["message"]
    assert data["error"]["details"]["weights_loaded"] is False


# ============================================================================
# 4. Attribute Adherence Arithmetic & Empty Set Tests
# ============================================================================
def test_attr_adherence_arithmetic_unit():
    """Verify mathematical correctness of attr_adherence calculation with mocked CLIP."""
    verifier = CLIPAttributeVerifier(device="cpu")
    verifier._initialized = True
    verifier._processor = MagicMock()

    # Mock model outputs returning distinct mock logits
    # For hair_length: ['bald', 'shaved', 'short', 'medium', 'long']
    # Logits: [4.0, 1.0, 1.0, 1.0, 1.0] -> softmax puts highest prob on 'bald'
    mock_model = MagicMock()
    mock_logits = torch.tensor([[4.0, 1.0, 1.0, 1.0, 1.0]])
    mock_model.return_value = MagicMock(logits_per_image=mock_logits)
    verifier._model = mock_model

    img = Image.new("RGB", (64, 64), color="white")
    results = verifier.verify_attributes(
        image=img,
        requested_attributes=["hair_length"],
        stated_attributes={"hair_length": "bald"},
    )

    probs = results["attribute_scores"]["hair_length"]
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-2)
    assert probs["bald"] > probs["long"]
    assert results["stated_probabilities"]["hair_length"] == probs["bald"]
    assert results["attr_adherence"] == probs["bald"]
    assert 0.0 <= results["attr_adherence"] <= 1.0


def test_attr_adherence_empty_stated_attributes():
    """
    Verify that when no stated attributes are provided, attr_adherence is None,
    stated_probabilities is empty, and zero division occurs.
    """
    verifier = CLIPAttributeVerifier(device="cpu")
    verifier._initialized = True
    verifier._processor = MagicMock()

    mock_model = MagicMock()
    mock_logits = torch.tensor([[1.0, 1.0, 1.0, 1.0, 1.0]])
    mock_model.return_value = MagicMock(logits_per_image=mock_logits)
    verifier._model = mock_model

    img = Image.new("RGB", (64, 64), color="white")
    results = verifier.verify_attributes(
        image=img,
        requested_attributes=["hair_length"],
        stated_attributes={},  # Empty stated attributes
    )

    assert results["stated_probabilities"] == {}
    assert results["attr_adherence"] is None  # Handled safely without arbitrary 1.0 default


def test_candidate_prompt_builders():
    """Verify probe prompt formatting across supported enums."""
    p_bald = build_candidate_prompt("hair_length", "bald")
    assert "bald" in p_bald

    p_male = build_candidate_prompt("sex_presentation", "male")
    assert "man" in p_male

    p_beard = build_candidate_prompt("facial_hair_type", "beard")
    assert "beard" in p_beard

    p_none_beard = build_candidate_prompt("facial_hair_type", "none")
    assert "clean-shaven" in p_none_beard


def test_generated_image_item_optional_adherence():
    """Verify backward-compatible optional attr_adherence field on GeneratedImageItem."""
    item = GeneratedImageItem(
        index=0,
        seed=42,
        image_base64="data:image/png;base64,abc",
        prompt_used="test prompt",
        width=512,
        height=512,
        label="variant_1",
        is_uncertain=False,
    )
    assert item.attr_adherence is None  # Defaults safely to None

    item_with_adherence = GeneratedImageItem(
        index=1,
        seed=43,
        image_base64="data:image/png;base64,abc",
        prompt_used="test prompt",
        width=512,
        height=512,
        label="variant_2",
        is_uncertain=False,
        attr_adherence=0.875,
    )
    assert item_with_adherence.attr_adherence == 0.875


# ============================================================================
# 5. Real CLIP Attribute Verification Integration Test (CPU-Safe)
# ============================================================================
@pytest.mark.integration
def test_real_clip_attribute_verifier_cpu():
    """
    Evaluates real CLIPModel on CPU verifying zero-shot attribute scoring and latency.
    Runs on CPU to strictly respect the 3276.3 MiB VRAM ceiling.
    """
    import time

    img = Image.new("RGB", (256, 256), color=(200, 200, 200))
    b64_uri = create_dummy_png_base64(256, 256, "gray")

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "image_b64": b64_uri,
        "image_id": "test-clip-img-001",
        "requested_attributes": ["hair_length", "sex_presentation"],
        "stated_attributes": {
            "hair_length": "bald",
            "sex_presentation": "male",
        },
    }

    t0 = time.perf_counter()
    response = client.post("/ml/v1/verify-attributes", json=payload, headers=headers)
    dt = time.perf_counter() - t0

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "ok"
    assert data["image_id"] == "test-clip-img-001"
    assert "hair_length" in data["attribute_scores"]
    assert "sex_presentation" in data["attribute_scores"]

    # Verify probabilities sum to ~1.0 per attribute
    hair_probs = data["attribute_scores"]["hair_length"]
    assert sum(hair_probs.values()) == pytest.approx(1.0, abs=1e-2)

    assert "hair_length" in data["stated_probabilities"]
    assert "sex_presentation" in data["stated_probabilities"]
    assert data["attr_adherence"] is not None
    assert 0.0 <= data["attr_adherence"] <= 1.0

    print(f"\n[Real CLIP CPU Verification] Latency: {dt:.2f}s, Adherence: {data['attr_adherence']}")
