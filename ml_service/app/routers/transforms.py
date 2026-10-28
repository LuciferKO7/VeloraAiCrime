"""
Forensic Transformation router for Velora ML Service.
Endpoint: POST /ml/v1/transform
Adheres to:
- MASTER_PROMPT.md §1 D7 (Transforms: age progression/regression, disguise removal, side profile)
- MASTER_PROMPT.md §11 Step A7
- contracts/schema.sql kind enum ('age', 'disguise', 'profile') and speculative flag
"""

import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator
from PIL import Image
import torch

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.masks.region_masker import region_masker
from ml_service.app.models.manager import model_manager
from ml_service.app.pipelines.sketch_prompts import SKETCH_NEGATIVE_PROMPT
from ml_service.app.routers.generate import encode_image_to_base64_uri
from ml_service.app.routers.verify import resolve_image_from_request
from ml_service.app.transforms.forensic_transforms import (
    DISGUISE_TARGETS,
    SUPPORTED_TRANSFORM_KINDS,
    transform_engine,
)

logger = logging.getLogger("velora.ml.transforms_router")
router = APIRouter(tags=["transforms"])


class TransformRequest(BaseModel):
    """Request payload for forensic composite transformations."""

    image_b64: Optional[str] = Field(None, description="Base64 encoded source image string or data URI")
    image_id: Optional[str] = Field(None, description="Optional associated image UUID")
    transform_kind: str = Field(..., description="One of: age_progression, age_regression, disguise_removal, side_profile")
    target_disguise: Optional[str] = Field(None, description="For disguise_removal: glasses, headwear, facial_hair, or all")
    age_delta_years: int = Field(20, ge=5, le=50, description="Years for age progression/regression")
    seed: int = Field(42, description="Random seed for reproducibility")
    strength: float = Field(0.70, ge=0.1, le=1.0, description="Transformation blend strength")

    @model_validator(mode="after")
    def validate_inputs(self) -> "TransformRequest":
        if not self.image_b64 and not self.image_id:
            raise ValueError("At least one of image_b64 or image_id must be provided")
        kind_clean = self.transform_kind.strip().lower()
        if kind_clean not in SUPPORTED_TRANSFORM_KINDS:
            raise ValueError(f"transform_kind must be one of {SUPPORTED_TRANSFORM_KINDS}; received '{self.transform_kind}'")
        if self.target_disguise and self.target_disguise.lower() not in (DISGUISE_TARGETS + ["all"]):
            raise ValueError(f"target_disguise must be one of {DISGUISE_TARGETS + ['all']}")
        return self


class TransformResponse(BaseModel):
    """Response payload for forensic composite transformations."""

    status: str = Field("ok", description="Status code string")
    image_base64: str = Field(..., description="Transformed composite sketch as PNG base64 data URI")
    transform_kind: str = Field(..., description="Applied transformation type")
    schema_kind: str = Field(..., description="Standard contracts/schema.sql kind: age, disguise, profile")
    speculative: bool = Field(..., description="Whether output is speculative per §11 R11 Invariant")
    seed_used: int = Field(..., description="RNG seed used for synthesis")
    prompt_used: str = Field(..., description="Prompt constructed for transformation")


@router.post(
    "/transform",
    response_model=TransformResponse,
    summary="Execute Forensic Transformation (Age, Disguise, Side Profile)",
    dependencies=[Depends(verify_service_key)],
)
async def execute_forensic_transform(req: TransformRequest) -> TransformResponse:
    """Executes forensic transformation with speculative labeling and style retention."""
    t0 = time.perf_counter()
    kind = req.transform_kind.strip().lower()
    logger.info("Received transform request: kind=%s, seed=%d", kind, req.seed)

    # 1. Resolve source image
    source_img = resolve_image_from_request(req.image_b64, req.image_id)
    width, height = source_img.size

    # 2. Build prompt and metadata
    prompt_text, target_region, is_speculative = transform_engine.build_transform_prompt(
        transform_kind=kind,
        target_disguise=req.target_disguise,
        age_delta_years=req.age_delta_years,
    )

    # Map to schema.sql kind ('age', 'disguise', 'profile')
    schema_kind_map = {
        "age_progression": "age",
        "age_regression": "age",
        "disguise_removal": "disguise",
        "side_profile": "profile",
    }
    schema_kind = schema_kind_map.get(kind, "edit")

    # 3. Execute generative transformation
    try:
        pipe = model_manager.load_pipeline(
            model_id=settings.DEFAULT_MODEL_ID,
            vae_id=settings.DEFAULT_VAE_ID,
            lcm_lora_id=settings.DEFAULT_LCM_LORA_ID,
        )

        use_cpu_generator = model_manager.low_vram_mode or "cuda" not in model_manager.device
        generator = torch.Generator(device="cpu" if use_cpu_generator else "cuda").manual_seed(req.seed)

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        res = pipe(
            prompt=prompt_text,
            negative_prompt=SKETCH_NEGATIVE_PROMPT,
            width=width,
            height=height,
            num_inference_steps=settings.ML_VARIANT_STEPS,
            guidance_scale=1.5,
            generator=generator,
        )

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        synth_img = res.images[0]

        # For side_profile: full synthesis.
        # For age/disguise: region blending via feathered mask.
        if kind == "side_profile":
            final_img = synth_img
        else:
            mask = region_masker.generate_region_mask(target_region, (width, height), feather_radius=12)
            final_img = Image.composite(synth_img, source_img, mask)

    except Exception as e:
        logger.error("Transform execution failed: %s", str(e), exc_info=True)
        raise MLError(
            code="INTERNAL",
            message=f"Failed to execute forensic transformation: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"error_type": type(e).__name__},
        )

    dt = time.perf_counter() - t0
    logger.info("Transform %s completed in %.2fs", kind, dt)

    return TransformResponse(
        status="ok",
        image_base64=encode_image_to_base64_uri(final_img),
        transform_kind=kind,
        schema_kind=schema_kind,
        speculative=is_speculative,
        seed_used=req.seed,
        prompt_used=prompt_text,
    )
