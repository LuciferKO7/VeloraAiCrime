"""
Unit tests for Milestone A5: Preference model and /evolve endpoint.
Covers:
- OnlinePreferenceModel initialization, update rules, and boundary clamping
- Exploration-to-exploitation variance decay across rounds
- Prompt modifier mapping
- Service-key authentication enforcement on POST /ml/v1/evolve
- Request schema validation
- Mocked multi-variant evolution execution
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from PIL import Image
import numpy as np

from ml_service.app.core.config import settings
from ml_service.app.main import app
from ml_service.app.models.manager import model_manager
from ml_service.app.preference.preference_model import RECOGNITION_AXES, preference_model

client = TestClient(app)


# ============================================================================
# 1. OnlinePreferenceModel Unit Tests
# ============================================================================
def test_preference_vector_initialization():
    """Verify clean zeroed initialization across all continuous recognition axes."""
    vec = preference_model.init_preference_vector()
    assert len(vec) == len(RECOGNITION_AXES)
    for axis in RECOGNITION_AXES:
        assert vec[axis] == 0.0


def test_preference_vector_update_like_and_dislike():
    """Verify that 'like' shifts positive and 'dislike' shifts negative."""
    init_vec = preference_model.init_preference_vector()

    # Apply 'like' on jaw_prominence and 'dislike' on eye_openness
    events = [
        {"event_type": "like", "variant_axes": {"jaw_prominence": 0.8, "eye_openness": 0.5}},
        {"event_type": "dislike", "variant_axes": {"cheek_fullness": 0.7, "eye_openness": 0.6}},
    ]

    updated = preference_model.update_preference_vector(init_vec, events)

    # jaw_prominence was liked with positive axis -> positive shift
    assert updated["jaw_prominence"] > 0.0

    # cheek_fullness was disliked with positive axis -> negative shift
    assert updated["cheek_fullness"] < 0.0

    # Values stay within [-1.0, 1.0]
    for val in updated.values():
        assert -1.0 <= val <= 1.0


def test_preference_vector_extreme_clamping():
    """Verify extreme feedback never pushes values outside [-1.0, 1.0]."""
    init_vec = preference_model.init_preference_vector()
    extreme_events = [{"event_type": "select", "variant_axes": {"jaw_prominence": 1.0}}] * 20
    updated = preference_model.update_preference_vector(init_vec, extreme_events)
    assert updated["jaw_prominence"] == 1.0


def test_sample_round_variants_variance_decay():
    """Verify variance decays over successive rounds (convergence property)."""
    pref_vec = preference_model.init_preference_vector()

    r1_variants = preference_model.sample_round_variants(pref_vec, round_number=1, num_variants=10, seed=100)
    r5_variants = preference_model.sample_round_variants(pref_vec, round_number=5, num_variants=10, seed=100)

    # Variant 0 is always the mean
    assert len(r1_variants) == 10
    assert len(r5_variants) == 10

    # Calculate standard deviation across sampled variants for round 1 vs round 5
    r1_stds = [np.std([v[axis] for v in r1_variants[1:]]) for axis in RECOGNITION_AXES]
    r5_stds = [np.std([v[axis] for v in r5_variants[1:]]) for axis in RECOGNITION_AXES]

    assert np.mean(r5_stds) < np.mean(r1_stds), "Exploration variance should decrease in later rounds"


def test_build_variant_prompt_modifiers():
    """Verify conversion of significant axis values into descriptive prompt tokens."""
    axes = {
        "jaw_prominence": 0.8,    # Should generate 'broad square jawline'
        "eye_openness": -0.7,     # Should generate 'narrow hooded eyes'
        "lip_fullness": 0.05,     # Sub-threshold (< 0.25), should not generate modifier
    }
    modifiers = preference_model.build_variant_prompt_modifiers(axes)
    assert len(modifiers) == 2
    assert "broad square jawline" in modifiers
    assert "narrow hooded eyes" in modifiers


# ============================================================================
# 2. POST /ml/v1/evolve Endpoint Tests
# ============================================================================
def test_evolve_auth_missing_header():
    """Verify 401 when X-Service-Key is omitted."""
    payload = {
        "session_id": "test-session-123",
        "round_number": 1,
        "base_attributes": {"age_band": "adult", "sex_presentation": "male"},
    }
    response = client.post("/ml/v1/evolve", json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_evolve_validation_missing_attributes():
    """Verify 422 when base_attributes is omitted."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "session_id": "test-session-123",
        "round_number": 1,
    }
    response = client.post("/ml/v1/evolve", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_evolve_execution_success(monkeypatch):
    """Verify successful 6-variant evolution execution with mocked pipeline."""
    mock_pipe = MagicMock()
    mock_variant = Image.new("RGB", (64, 64), color="gray")
    mock_pipe.return_value = MagicMock(images=[mock_variant])
    monkeypatch.setattr(model_manager, "load_pipeline", lambda **kwargs: mock_pipe)

    headers = {"X-Service-Key": settings.SERVICE_KEY}
    payload = {
        "session_id": "sess-uuid-456",
        "round_number": 2,
        "base_attributes": {
            "age_band": {"value": "young_adult"},
            "sex_presentation": {"value": "female"},
            "hair": {"value": "shoulder length dark hair"},
        },
        "feedback_events": [
            {
                "image_id": "img-001",
                "event_type": "like",
                "variant_axes": {"jaw_prominence": 0.5, "eye_openness": 0.4},
            }
        ],
        "num_variants": 6,
        "seed": 999,
        "image_size": 64,
    }

    response = client.post("/ml/v1/evolve", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["session_id"] == "sess-uuid-456"
    assert data["round_number"] == 2
    assert isinstance(data["preference_vector"], dict)
    assert data["preference_vector"]["jaw_prominence"] > 0.0

    assert len(data["variants"]) == 6
    for idx, var in enumerate(data["variants"]):
        assert var["variant_index"] == idx
        assert "data:image/png;base64," in var["image_base64"]
        assert isinstance(var["variant_axes"], dict)
        assert len(var["variant_axes"]) == len(RECOGNITION_AXES)
