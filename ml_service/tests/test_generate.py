"""
Comprehensive test suite for Step A2: Image Generation Engine (/ml/v1/generate).
Tests:
- Prompt construction for Option A (facial composite) and Option B (incident storyboard).
- Authentication enforcement (X-Service-Key).
- Schema validation and limits (max frame count, required module-specific fields).
- Unit tests with mock pipeline verifying dispatch, seed progression, encoding, and error schemas.
- Real pipeline integration test verifying end-to-end generation, 512x512 resolution, and VRAM budget.
"""

import base64
import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image

from ml_service.app.core.config import settings
from ml_service.app.main import app
from ml_service.app.pipelines.sketch_prompts import (
    MANDATORY_BASE_NEGATIVE_TOKENS,
    SKETCH_NEGATIVE_PROMPT,
    build_facial_composite_prompt,
    build_storyboard_frame_prompt,
)

client = TestClient(app)


# ============================================================================
# 1. Prompt Engineering & Invariant Unit Tests
# ============================================================================
def test_mandatory_base_negative_tokens_preserved():
    """Verify all 10 base negative tokens from §9.3.4 are preserved in exact order."""
    neg_prompt = SKETCH_NEGATIVE_PROMPT
    for token in MANDATORY_BASE_NEGATIVE_TOKENS:
        assert token in neg_prompt, f"Mandatory token '{token}' missing from negative prompt!"

    # Verify head order
    tokens_in_prompt = [t.strip() for t in neg_prompt.split(",")]
    assert tokens_in_prompt[:10] == MANDATORY_BASE_NEGATIVE_TOKENS


def test_facial_composite_prompt_construction():
    """Verify facial sketch prompt properly maps witness descriptors."""
    attrs = {
        "age_band": {"value": "young_adult"},
        "sex_presentation": {"value": "man"},
        "face_shape": {"value": "square"},
        "jawline": {"value": "angular"},
        "eyes": {"value": "dark brown"},
        "eyebrows": {"value": "thick arched"},
        "nose": {"value": "straight narrow"},
        "mouth": {"value": "medium"},
        "hair": {"value": "short wavy dark"},
        "facial_hair": {"value": "light stubble"},
        "distinguishing_features": {"value": "scar on chin"},
    }
    prompt = build_facial_composite_prompt(attrs)
    assert "forensic pencil sketch" in prompt
    assert "monochrome graphite" in prompt
    assert "young adult man" in prompt
    assert "wearing plain crewneck shirt covering shoulders" in prompt
    assert "square face" in prompt
    assert "angular jawline" in prompt
    assert "scar on chin" in prompt
    assert "clean neutral background" in prompt


def test_storyboard_frame_prompt_construction():
    """Verify storyboard frame prompt properly formats action, setting, and uncertainty."""
    # Frame 1: Confirmed action
    p1 = build_storyboard_frame_prompt(
        event_description="Subject in dark hoodie enters the convenience store",
        action="entering through door",
        characters=["tall male in hoodie"],
        objects=["glass door"],
        location="store entrance",
        is_uncertain=False,
    )
    assert "forensic incident storyboard sketch" in p1
    assert "entering through door" in p1
    assert "setting: store entrance" in p1
    assert "figures: tall male in hoodie" in p1
    assert "objects: glass door" in p1
    assert "crisp pencil contours" in p1

    # Frame 2: Speculative action
    p2 = build_storyboard_frame_prompt(
        event_description="Subject reaches towards the counter display",
        action="reaching",
        location="cash register counter",
        is_uncertain=True,
    )
    assert "speculative sketch rendering" in p2
    assert "soft illustrative pencil lines" in p2


# ============================================================================
# 2. Authentication & Authorization Tests
# ============================================================================
def test_generate_auth_missing_header():
    """Verify POST /ml/v1/generate rejects requests without X-Service-Key."""
    payload = {
        "module_type": "facial_composite",
        "facial_attributes": {"age_band": {"value": "adult"}},
    }
    response = client.post("/ml/v1/generate", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_generate_auth_invalid_header():
    """Verify POST /ml/v1/generate rejects requests with wrong service key."""
    headers = {"X-Service-Key": "wrong-key"}
    payload = {
        "module_type": "facial_composite",
        "facial_attributes": {"age_band": {"value": "adult"}},
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


# ============================================================================
# 3. Schema Validation & Guardrail Tests
# ============================================================================
def test_generate_validation_missing_facial_attributes():
    """Verify 422 when facial_attributes is missing for facial_composite."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "facial_composite",
        # Missing facial_attributes
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_validation_missing_storyboard_events():
    """Verify 422 when storyboard_events is missing for incident_storyboard."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "incident_storyboard",
        # Missing storyboard_events
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_validation_excessive_storyboard_frames():
    """Verify 422 when storyboard exceeds maximum of 6 frames."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    events = [
        {"frame_index": i, "description": f"Event description {i}"}
        for i in range(1, 8)  # 7 frames (limit is 6)
    ]
    payload = {
        "module_type": "incident_storyboard",
        "storyboard_events": events,
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ============================================================================
# 4. Unit Tests with Mock Pipeline (Fast Logic & Dispatch Verification)
# ============================================================================
def create_dummy_pil_image(width=512, height=512):
    """Helper to generate a lightweight PIL image for mock tests."""
    return Image.new("RGB", (width, height), color=(240, 240, 240))


@patch("ml_service.app.models.manager.model_manager.load_pipeline")
def test_generate_facial_composite_unit(mock_load_pipeline):
    """Verify facial composite generation dispatch, seed progression, and response format."""
    mock_pipe = MagicMock()
    mock_pipe.return_value = MagicMock(images=[create_dummy_pil_image()])
    mock_load_pipeline.return_value = mock_pipe

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "facial_composite",
        "case_id": "test-case-1234",
        "seed": 100,
        "num_variants": 3,
        "image_size": 512,
        "facial_attributes": {
            "age_band": {"value": "adult"},
            "sex_presentation": {"value": "man"},
            "hair": {"value": "dark short"},
        },
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "ok"
    assert data["module_type"] == "facial_composite"
    assert data["case_id"] == "test-case-1234"
    assert data["count"] == 3
    assert len(data["images"]) == 3
    assert data["disclaimer"] == settings.DISCLAIMER_V1

    # Verify seed progression and base64 encoding
    for idx, item in enumerate(data["images"]):
        assert item["index"] == idx
        assert item["seed"] == 100 + (idx * 997)
        assert item["image_base64"].startswith("data:image/png;base64,")
        assert item["width"] == 512
        assert item["height"] == 512
        assert item["label"] == f"variant_{idx + 1}"
        assert item["is_uncertain"] is False


@patch("ml_service.app.models.manager.model_manager.load_pipeline")
def test_generate_incident_storyboard_unit(mock_load_pipeline):
    """Verify incident storyboard sequential frame dispatch and ordering."""
    mock_pipe = MagicMock()
    mock_pipe.return_value = MagicMock(images=[create_dummy_pil_image()])
    mock_load_pipeline.return_value = mock_pipe

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "incident_storyboard",
        "case_id": "storyboard-case-5678",
        "seed": 2024,
        "image_size": 512,
        "storyboard_events": [
            {
                "frame_index": 1,
                "description": "Suspect enters the store",
                "action": "entering",
                "location": "entrance",
                "is_uncertain": False,
            },
            {
                "frame_index": 2,
                "description": "Suspect takes a backpack from the counter",
                "action": "taking bag",
                "objects": ["backpack"],
                "is_uncertain": True,
            },
            {
                "frame_index": 3,
                "description": "Suspect runs out toward the alley",
                "action": "running away",
                "location": "alley",
                "is_uncertain": False,
            },
        ],
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "ok"
    assert data["module_type"] == "incident_storyboard"
    assert data["count"] == 3
    assert len(data["images"]) == 3

    # Check frame ordering and uncertainty labeling
    assert data["images"][0]["index"] == 1
    assert data["images"][0]["label"] == "frame_1"
    assert data["images"][0]["is_uncertain"] is False

    assert data["images"][1]["index"] == 2
    assert data["images"][1]["label"] == "frame_2"
    assert data["images"][1]["is_uncertain"] is True

    assert data["images"][2]["index"] == 3
    assert data["images"][2]["label"] == "frame_3"
    assert data["images"][2]["is_uncertain"] is False


@patch("ml_service.app.models.manager.model_manager.load_pipeline")
def test_generate_pipeline_load_failure(mock_load_pipeline):
    """Verify 503 ML_UNAVAILABLE returned when pipeline fails to load."""
    mock_load_pipeline.side_effect = RuntimeError("CUDA out of memory error during weight allocation")

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "facial_composite",
        "facial_attributes": {"age_band": {"value": "adult"}},
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "ML_UNAVAILABLE"
    assert "failed to load" in data["error"]["message"]


# ============================================================================
# 5. Real Model Integration Test
# ============================================================================
@pytest.mark.integration
def test_generate_real_model_facial_composite_e2e():
    """
    End-to-end integration test with real PyTorch model weights.
    Generates 1 single-frame sketch to verify real CUDA execution, resolution, and VRAM.
    """
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "facial_composite",
        "case_id": "real-integration-case-001",
        "seed": 42,
        "num_variants": 1,
        "image_size": 512,
        "num_inference_steps": 3,
        "guidance_scale": 1.5,
        "facial_attributes": {
            "age_band": {"value": "adult"},
            "sex_presentation": {"value": "man"},
            "face_shape": {"value": "oval"},
            "hair": {"value": "short black"},
        },
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 200, f"Real generation failed: {response.text}"
    data = response.json()

    assert data["status"] == "ok"
    assert data["count"] == 1
    assert data["latency_sec"] > 0.0
    assert data["peak_vram_mb"] < 3276.3, f"VRAM exceeded budget: {data['peak_vram_mb']} MiB"

    item = data["images"][0]
    assert item["width"] == 512
    assert item["height"] == 512
    assert item["image_base64"].startswith("data:image/png;base64,")

    # Decode base64 to confirm valid PNG structure
    raw_b64 = item["image_base64"].split(",", 1)[1]
    img_bytes = base64.b64decode(raw_b64)
    pil_img = Image.open(io.BytesIO(img_bytes))
    assert pil_img.format == "PNG"
    assert pil_img.size == (512, 512)


@pytest.mark.integration
def test_generate_real_model_incident_storyboard_e2e():
    """
    End-to-end integration test with real PyTorch model weights for incident storyboard.
    Generates 1 single storyboard frame to verify narrative prompt execution, dimensions, and latency.
    """
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "module_type": "incident_storyboard",
        "case_id": "real-integration-case-002",
        "seed": 101,
        "image_size": 512,
        "num_inference_steps": 3,
        "guidance_scale": 1.5,
        "storyboard_events": [
            {
                "frame_index": 1,
                "description": "Suspect in dark jacket approaches the glass counter",
                "action": "approaching counter",
                "characters": ["person in dark jacket"],
                "objects": ["counter display"],
                "location": "convenience store",
                "is_uncertain": False,
            }
        ],
    }
    response = client.post("/ml/v1/generate", json=payload, headers=headers)
    assert response.status_code == 200, f"Real storyboard generation failed: {response.text}"
    data = response.json()

    assert data["status"] == "ok"
    assert data["module_type"] == "incident_storyboard"
    assert data["count"] == 1
    assert data["latency_sec"] > 0.0
    assert data["peak_vram_mb"] < 3276.3

    item = data["images"][0]
    assert item["index"] == 1
    assert item["label"] == "frame_1"
    assert item["width"] == 512
    assert item["height"] == 512
    assert item["image_base64"].startswith("data:image/png;base64,")
