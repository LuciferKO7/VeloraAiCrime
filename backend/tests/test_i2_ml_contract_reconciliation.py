import base64
import math
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["SERVICE_KEY"] = "test_service_key_for_testing_1234567890"
os.environ["JWT_SECRET"] = "test_jwt_secret_min_32_characters_long_for_velora"

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.services.ml_proxy import (
    CANONICAL_REGIONS,
    MINIMAL_PNG_BYTES,
    MLProxyClient,
    decode_image_base64,
    resolve_canonical_region,
)


@pytest.fixture
def temp_storage(tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    orig_storage = settings.STORAGE_DIR
    settings.STORAGE_DIR = str(storage_dir)
    yield storage_dir
    settings.STORAGE_DIR = orig_storage


def test_i2_1_decode_image_base64_valid_and_invalid():
    """Unit test for base64 and data-URI decoding and safety guards."""
    raw_png = MINIMAL_PNG_BYTES
    b64_plain = base64.b64encode(raw_png).decode("ascii")
    b64_data_uri = f"data:image/png;base64,{b64_plain}"

    # Valid data-URI
    decoded_uri = decode_image_base64(b64_data_uri)
    assert decoded_uri == raw_png

    # Valid plain base64
    decoded_plain = decode_image_base64(b64_plain)
    assert decoded_plain == raw_png

    # Invalid empty or whitespace string
    with pytest.raises(ValueError, match="Empty or non-string"):
        decode_image_base64("")

    with pytest.raises(ValueError, match="Empty or non-string"):
        decode_image_base64("   \n\t  ")

    # Corrupt base64
    with pytest.raises(ValueError, match="Malformed base64"):
        decode_image_base64("data:image/png;base64,not_valid_base64!!!")


def test_i2_2_resolve_canonical_region_rules():
    """Unit test verifying canonical region detection and ambiguous rejection."""
    assert sorted(CANONICAL_REGIONS) == [
        "cheeks",
        "eyebrows",
        "eyes",
        "forehead",
        "hair",
        "jaw",
        "mouth",
        "nose",
    ]

    # Explicit canonical regions
    assert resolve_canonical_region(explicit_region="nose") == "nose"
    assert resolve_canonical_region(explicit_region="HAIR") == "hair"
    assert resolve_canonical_region(explicit_region="Jaw") == "jaw"

    # Unsupported explicit region
    with pytest.raises(AppError) as exc_info:
        resolve_canonical_region(explicit_region="neck")
    assert exc_info.value.status_code == 400
    assert "Region 'neck' is not supported" in exc_info.value.message

    # Unambiguous instruction parsing
    assert resolve_canonical_region("make the nose sharper and thinner") == "nose"
    assert resolve_canonical_region("thicker arched eyebrows") == "eyebrows"
    assert resolve_canonical_region("curly spiky hair with receding hairline") == "hair"
    assert resolve_canonical_region("fuller lips and wider smile") == "mouth"
    assert resolve_canonical_region("pointed chin and angular jaw") == "jaw"
    assert resolve_canonical_region("higher cheekbones") == "cheeks"
    assert resolve_canonical_region("high forehead") == "forehead"

    # Ambiguous instruction with multiple regions -> fail closed
    with pytest.raises(AppError) as exc_info:
        resolve_canonical_region("make the eyes larger and nose smaller")
    assert exc_info.value.status_code == 400
    assert "Ambiguous anatomical region" in exc_info.value.message

    # Ambiguous instruction with zero identifiable regions -> fail closed
    with pytest.raises(AppError) as exc_info:
        resolve_canonical_region("make the suspect look more suspicious and older")
    assert exc_info.value.status_code == 400
    assert "Could not identify a canonical anatomical region" in exc_info.value.message

    # Custom mask provided without explicit region -> allowed
    assert resolve_canonical_region(mask_b64="data:image/png;base64,fake") is None


def test_i2_3_generation_request_mapping_and_response_parsing(temp_storage):
    """
    Unit test verifying that generate_initial_round maps to Person A's GenerateRequest schema:
    module_type='facial_composite', facial_attributes, and parses GenerateResponse images[].
    """
    client = MLProxyClient(base_url="http://test-ml:8001", service_key="test-key")

    b64_png = f"data:image/png;base64,{base64.b64encode(MINIMAL_PNG_BYTES).decode('ascii')}"
    ml_response_payload = {
        "status": "ok",
        "module_type": "facial_composite",
        "case_id": "case-uuid-123",
        "disclaimer": "AI-generated investigative aid",
        "count": 2,
        "images": [
            {
                "index": 0,
                "seed": 42,
                "image_base64": b64_png,
                "prompt_used": "forensic sketch of male face",
                "width": 512,
                "height": 512,
                "label": "variant_1",
                "is_uncertain": False,
                "attr_adherence": 0.89,
            },
            {
                "index": 1,
                "seed": 1039,
                "image_base64": b64_png,
                "prompt_used": "forensic sketch of male face, variant 2",
                "width": 512,
                "height": 512,
                "label": "variant_2",
                "is_uncertain": False,
                "attr_adherence": 0.85,
            },
        ],
        "latency_sec": 1.45,
        "peak_vram_mb": 619.8,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = ml_response_payload

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        results = client.generate_initial_round(
            session_id="session-456",
            round_id="round-789",
            round_no=1,
            attributes={"sex_presentation": "male", "age_band": "adult"},
            num_variants=2,
            seed=42,
            case_id="case-uuid-123",
        )

    # Check request payload sent
    mock_post.assert_called_once()
    called_url, called_kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert called_url == "http://test-ml:8001/ml/v1/generate"
    assert called_kwargs["headers"]["X-Service-Key"] == "test-key"

    sent_body = called_kwargs["json"]
    assert sent_body["module_type"] == "facial_composite"
    assert sent_body["facial_attributes"] == {"sex_presentation": "male", "age_band": "adult"}
    assert sent_body["num_variants"] == 2
    assert sent_body["seed"] == 42
    assert sent_body["case_id"] == "case-uuid-123"

    # Check parsed results
    assert len(results) == 2
    assert results[0]["variant_index"] == 0
    assert results[0]["prompt_text"] == "forensic sketch of male face"
    assert results[0]["attr_adherence"] == 0.89
    assert results[0]["width"] == 512
    assert results[0]["session_id"] == "session-456"
    assert results[0]["round_id"] == "round-789"
    assert results[1]["variant_index"] == 1


def test_i2_4_evolution_request_mapping(temp_storage):
    """
    Unit test verifying that evolve_round maps fields to Person A's EvolveRequest schema:
    round_number, base_attributes, feedback_events, and parses EvolveResponse variants[].
    """
    client = MLProxyClient(base_url="http://test-ml:8001", service_key="test-key")

    b64_png = f"data:image/png;base64,{base64.b64encode(MINIMAL_PNG_BYTES).decode('ascii')}"
    ml_evolve_payload = {
        "status": "ok",
        "session_id": "session-456",
        "round_number": 2,
        "preference_vector": {"jaw_width": 0.65},
        "variants": [
            {
                "variant_index": 0,
                "seed": 1042,
                "image_base64": b64_png,
                "variant_axes": {"jaw_width": 0.65},
                "prompt_used": "forensic sketch evolved variant 1",
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = ml_evolve_payload

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        results = client.evolve_round(
            session_id="session-456",
            round_id="round-2",
            round_no=2,
            parent_round_id="round-1",
            feedback={"picked": ["img-0"], "events": [{"variant_index": 0, "action": "pick"}]},
            attributes={"face_shape": "oval"},
            num_variants=2,
            seed=42,
            case_id="case-uuid-123",
        )

    mock_post.assert_called_once()
    sent_body = mock_post.call_args[1]["json"]
    assert sent_body["round_number"] == 2
    assert sent_body["base_attributes"] == {"face_shape": "oval"}
    assert sent_body["feedback_events"] == [{"variant_index": 0, "action": "pick"}]
    assert sent_body["session_id"] == "session-456"

    assert len(results) == 1
    assert results[0]["variant_index"] == 0
    assert results[0]["prompt_text"] == "forensic sketch evolved variant 1"


def test_i2_5_edit_request_mapping(temp_storage):
    """
    Unit test verifying that edit_round maps to Person A's EditRequest schema:
    image_id, region, edit_instruction, and parses EditResponse.
    """
    client = MLProxyClient(base_url="http://test-ml:8001", service_key="test-key")

    b64_png = f"data:image/png;base64,{base64.b64encode(MINIMAL_PNG_BYTES).decode('ascii')}"
    ml_edit_payload = {
        "status": "ok",
        "image_base64": b64_png,
        "mask_used_base64": b64_png,
        "region": "nose",
        "seed_used": 9999,
        "prompt_used": "forensic modification of nose, make nose sharper",
        "attr_adherence": 0.92,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = ml_edit_payload

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        results = client.edit_round(
            session_id="session-456",
            round_id="round-3",
            round_no=3,
            parent_image_id="parent-img-uuid",
            instruction_text="make nose sharper",
            kind="edit",
        )

    mock_post.assert_called_once()
    sent_body = mock_post.call_args[1]["json"]
    assert sent_body["image_id"] == "parent-img-uuid"
    assert sent_body["region"] == "nose"
    assert sent_body["edit_instruction"] == "make nose sharper"

    assert len(results) == 1
    assert results[0]["kind"] == "edit"
    assert results[0]["parent_image_id"] == "parent-img-uuid"
    assert results[0]["attr_adherence"] == 0.92


def test_i2_6_json_embedding_request():
    """
    Unit test verifying that get_embedding sends a JSON payload with image_b64
    to POST /ml/v1/embed, and enforces 512-dim L2 normalization.
    """
    client = MLProxyClient(base_url="http://test-ml:8001", service_key="test-key")

    # Construct raw 512 vector with magnitude 2.0
    raw_vec = [2.0 / math.sqrt(512)] * 512
    ml_embed_payload = {
        "status": "ok",
        "image_id": "test-img-uuid",
        "embedding": raw_vec,
        "embedding_l2_norm": 1.0,
        "dimension": 512,
        "model_version": "arcface-r100-v1",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = ml_embed_payload

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        emb, model_ver = client.get_embedding(MINIMAL_PNG_BYTES, image_id="test-img-uuid")

    mock_post.assert_called_once()
    called_url, called_kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert called_url == "http://test-ml:8001/ml/v1/embed"

    sent_json = called_kwargs["json"]
    assert sent_json["image_id"] == "test-img-uuid"
    assert sent_json["image_b64"].startswith("data:image/png;base64,")

    # Verify returned embedding is L2-normalized
    assert len(emb) == 512
    norm = math.sqrt(sum(x * x for x in emb))
    assert abs(norm - 1.0) < 1e-4
    assert model_ver == "arcface-r100-v1"


def test_i2_7_health_url_and_service_key():
    """
    Unit test verifying that the ML health probe targets /ml/v1/health
    with X-Service-Key and 2s timeout.
    """
    client = MLProxyClient(base_url="http://test-ml:8001", service_key="secret-key-123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ok",
        "service": "ml_service",
        "cuda_available": False,
        "device": "cpu",
    }

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        health_data = client.check_health()

    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == "http://test-ml:8001/ml/v1/health"
    assert mock_get.call_args[1]["headers"]["X-Service-Key"] == "secret-key-123"
    assert health_data["status"] == "ok"

    # Test error status code
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 401
    with patch("httpx.Client.get", return_value=mock_err_resp):
        err_health = client.check_health()
    assert err_health["status"] == "down"
