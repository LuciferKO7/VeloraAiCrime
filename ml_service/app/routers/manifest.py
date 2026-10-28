"""
Model manifest endpoint for Velora ML Service.
Adheres to:
- docs/CONTRACT_CHANGES.md v1.1 addendum (#3):
  "Added ML route GET /ml/v1/manifest returning model metadata list [{name, role, version, source, license, checksum}]."
- MASTER_PROMPT.md §6.3 (auth via X-Service-Key)
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings

logger = logging.getLogger("velora.ml.manifest")
router = APIRouter(tags=["manifest"])


class ModelManifestItem(BaseModel):
    """Metadata item for a registered ML model."""

    name: str = Field(..., description="Canonical model identifier")
    role: str = Field(..., description="Role in pipeline: face_generator, attribute_verifier, face_embedder, inpainter, upscaler")
    version: str = Field(..., description="Model version string or checkpoint tag")
    source: str = Field(..., description="HuggingFace repository ID, local path, or vendor source")
    license: str = Field(..., description="Exact weight licensing terms (e.g. CreativeML OpenRAIL-M, MIT, DeepInsight Research-Only)")
    checksum: Optional[str] = Field(None, description="SHA256 checksum of weights if known/pinned")
    is_loaded: bool = Field(False, description="Whether model weights are currently resident in memory")


class ManifestResponse(BaseModel):
    """Response payload for GET /ml/v1/manifest."""

    status: str = Field("ok", description="Status code string")
    models: List[ModelManifestItem] = Field(..., description="List of registered model metadata records")


@router.get(
    "/manifest",
    response_model=ManifestResponse,
    summary="Get ML Service Model Registry Manifest",
    dependencies=[Depends(verify_service_key)],
)
async def get_model_manifest() -> ManifestResponse:
    """Returns the metadata catalog of all models configured in the ML service."""
    from ml_service.app.models.manager import model_manager
    from ml_service.app.pipelines.attribute_verifier import attribute_verifier
    from ml_service.app.pipelines.face_embedder import face_embedder

    # Query active pipeline state
    sd_active = model_manager.is_loaded
    clip_active = getattr(attribute_verifier, "_initialized", False)
    arcface_active = face_embedder.is_loaded

    catalog = [
        ModelManifestItem(
            name="Realistic_Vision_V5.1_noVAE",
            role="face_generator",
            version="v5.1-lcm-lora",
            source=settings.DEFAULT_MODEL_ID,
            license="CreativeML OpenRAIL-M",
            checksum=None,
            is_loaded=sd_active,
        ),
        ModelManifestItem(
            name="clip-vit-base-patch32",
            role="attribute_verifier",
            version="openai-clip-v1",
            source="openai/clip-vit-base-patch32",
            license="MIT",
            checksum=None,
            is_loaded=clip_active,
        ),
        ModelManifestItem(
            name="arcface-r100",
            role="face_embedder",
            version="arcface-onnx-v1",
            source="insightface/buffalo_s or onnx-model-zoo/arcface",
            license="DeepInsight Non-Commercial / MIT",
            checksum=None,
            is_loaded=arcface_active,
        ),
        ModelManifestItem(
            name="stable-diffusion-inpainting",
            role="inpainter",
            version="sd-v1.5-inpainting-lcm",
            source="runwayml/stable-diffusion-inpainting or latent-blending",
            license="CreativeML OpenRAIL-M",
            checksum=None,
            is_loaded=False,
        ),
        ModelManifestItem(
            name="bicubic-lanczos-sharpener",
            role="upscaler",
            version="pil-lanczos-2x-v1",
            source="internal-pillow",
            license="HPND (PIL)",
            checksum=None,
            is_loaded=True,
        ),
    ]

    return ManifestResponse(status="ok", models=catalog)
