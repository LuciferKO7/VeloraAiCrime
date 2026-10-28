"""
Pytest test suite for Step A1: ML Service Skeleton.
Verifies TA1.1 through TA1.5 per MASTER_PROMPT.md.
"""

import pytest
from fastapi.testclient import TestClient

from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.main import app
from ml_service.app.models.manager import model_manager

client = TestClient(app)


# ============================================================================
# TA1.1: Service Launch & Route Registration
# ============================================================================
def test_ta1_1_service_initialization():
    """Verify that FastAPI app initializes properly with title and /ml/v1 routes."""
    assert app.title == "Velora ML Service"
    assert app.version == "1.0.0"

    # Confirm /ml/v1/health route is registered
    openapi_schema = app.openapi()
    assert "/ml/v1/health" in openapi_schema["paths"], f"Expected /ml/v1/health in openapi paths: {openapi_schema['paths'].keys()}"


# ============================================================================
# TA1.2: Health Endpoint & Telemetry
# ============================================================================
def test_ta1_2_health_endpoint_success():
    """Verify GET /ml/v1/health returns valid telemetry when authenticated."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    response = client.get("/ml/v1/health", headers=headers)

    assert response.status_code == 200, f"Expected 200, got: {response.status_code} - {response.text}"
    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "ml_service"
    assert data["version"] == "1.0.0"
    assert isinstance(data["cuda_available"], bool)
    assert isinstance(data["device"], str)
    assert isinstance(data["vram_total_mb"], (int, float))
    assert isinstance(data["vram_allocated_mb"], (int, float))
    assert isinstance(data["vram_reserved_mb"], (int, float))
    assert isinstance(data["low_vram_mode"], bool)
    assert data["disclaimer"] == settings.DISCLAIMER_V1
    assert "AI-generated investigative aid" in data["disclaimer"]


# ============================================================================
# TA1.3: Service-to-Service Authentication
# ============================================================================
def test_ta1_3_auth_missing_header():
    """Verify request without X-Service-Key is rejected with 401 AUTH_INVALID."""
    response = client.get("/ml/v1/health")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "AUTH_INVALID"
    assert "Missing" in data["error"]["message"] or "Invalid" in data["error"]["message"]


def test_ta1_3_auth_invalid_header():
    """Verify request with incorrect X-Service-Key is rejected with 401 AUTH_INVALID."""
    headers = {"X-Service-Key": "completely-invalid-secret-key-12345"}
    response = client.get("/ml/v1/health", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "AUTH_INVALID"
    assert "Invalid service key" in data["error"]["message"]


def test_ta1_3_auth_empty_header():
    """Verify request with empty X-Service-Key is rejected with 401 AUTH_INVALID."""
    headers = {"X-Service-Key": ""}
    response = client.get("/ml/v1/health", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "AUTH_INVALID"


# ============================================================================
# TA1.4: ModelManager & Memory Lifecycle
# ============================================================================
def test_ta1_4_model_manager_status():
    """Verify ModelManager queries real memory stats without mock data."""
    mem_status = model_manager.get_memory_status()
    assert "cuda_available" in mem_status
    assert "device" in mem_status
    assert "low_vram_mode" in mem_status
    assert "vram_total_mb" in mem_status
    assert "vram_allocated_mb" in mem_status
    assert isinstance(mem_status["vram_allocated_mb"], (int, float))


def test_ta1_4_model_manager_unload():
    """Verify unload_active_model safely clears pipeline state and caches."""
    # Ensure unload runs without error even when no model is currently active
    model_manager.unload_active_model()
    assert model_manager.active_model_id is None
    assert model_manager.is_loaded is False


# ============================================================================
# TA1.5: Standardized Error Handling (§6.3)
# ============================================================================
def test_ta1_5_error_format_not_found():
    """Verify 404 error adheres strictly to MASTER_PROMPT.md §6.3 error schema."""
    response = client.get("/ml/v1/nonexistent-route-for-testing")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]
    assert "details" in data["error"]


def test_ta1_5_custom_ml_error():
    """Verify custom MLError conforms to §6.3 structure."""
    from fastapi import Request

    err = MLError(code="ML_BUSY", message="GPU inference queue full", status_code=503, details={"queue_length": 5})
    assert err.code == "ML_BUSY"
    assert err.status_code == 503
    assert err.details["queue_length"] == 5


# ============================================================================
# Contract Addendum v1.1: Model Manifest Endpoint
# ============================================================================
def test_manifest_endpoint_unauthorized():
    """Verify GET /ml/v1/manifest rejects requests without valid service key."""
    response = client.get("/ml/v1/manifest")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_manifest_endpoint_success():
    """Verify GET /ml/v1/manifest returns model catalog matching schema."""
    headers = {"X-Service-Key": settings.SERVICE_KEY}
    response = client.get("/ml/v1/manifest", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["models"], list)
    assert len(data["models"]) >= 4

    roles = {m["role"] for m in data["models"]}
    assert "face_generator" in roles
    assert "attribute_verifier" in roles
    assert "face_embedder" in roles

    for m in data["models"]:
        assert "name" in m
        assert "version" in m
        assert "license" in m
        assert "source" in m
