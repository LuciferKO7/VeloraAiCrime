"""
Facial Region Editing / Inpainting router for Velora ML Service.
Endpoint: POST /ml/v1/edit
Adheres to:
- MASTER_PROMPT.md §11 Step A4
- Region masking via ml_service/app/masks/region_masker.py
- Standardized error and auth contracts (§6.3)
"""

import base64
import io
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator
from PIL import Image, ImageOps
import torch

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.masks.region_masker import CANONICAL_REGIONS, region_masker
from ml_service.app.models.manager import model_manager
from ml_service.app.pipelines.attribute_verifier import ATTRIBUTE_ENUM_REGISTRY, attribute_verifier
from ml_service.app.pipelines.sketch_prompts import (
    SKETCH_NEGATIVE_PROMPT,
    build_facial_composite_prompt,
)
from ml_service.app.routers.generate import encode_image_to_base64_uri
from ml_service.app.routers.verify import decode_base64_image, resolve_image_from_request

logger = logging.getLogger("velora.ml.edit")
router = APIRouter(tags=["edit"])

SKETCH_BASE_STYLE_POSITIVE: str = "forensic pencil sketch, monochrome graphite drawing on paper"


class EditRequest(BaseModel):
    """Request payload for facial region editing / inpainting."""

    image_b64: Optional[str] = Field(None, description="Base64 encoded source image string or data URI")
    image_id: Optional[str] = Field(None, description="Optional associated image UUID")
    region: Optional[str] = Field(None, description="Target anatomical region: hair, eyes, eyebrows, nose, mouth, jaw, cheeks, forehead")
    mask_b64: Optional[str] = Field(None, description="Optional custom base64 encoded binary mask")
    edit_instruction: Optional[str] = Field(None, description="Natural language edit description (e.g. 'thicker arched eyebrows')")
    updated_attributes: Optional[Dict[str, Any]] = Field(None, description="Structured attributes dictionary to incorporate")
    seed: int = Field(42, description="Random seed for reproducible generation")
    strength: float = Field(0.75, ge=0.1, le=1.0, description="Denoising / modification strength in [0.1, 1.0]")
    feather_radius: int = Field(8, ge=0, le=32, description="Gaussian blur feathering radius for mask edges")

    @model_validator(mode="after")
    def validate_inputs(self) -> "EditRequest":
        if not self.image_b64 and not self.image_id:
            raise ValueError("At least one of image_b64 or image_id must be provided")
        if not self.region and not self.mask_b64:
            raise ValueError(f"At least one of region (one of {CANONICAL_REGIONS}) or mask_b64 must be provided")
        if self.region and self.region.lower() not in CANONICAL_REGIONS:
            raise ValueError(f"Region '{self.region}' is not supported. Supported regions: {CANONICAL_REGIONS}")
        if not self.edit_instruction and not self.updated_attributes:
            raise ValueError("At least one of edit_instruction or updated_attributes must be provided")
        return self


class EditResponse(BaseModel):
    """Response payload for facial region editing."""

    status: str = Field("ok", description="Status code string")
    image_base64: str = Field(..., description="Edited composite sketch as PNG base64 data URI")
    mask_used_base64: str = Field(..., description="Binary mask used for inpainting as PNG base64 data URI")
    region: Optional[str] = Field(None, description="Target anatomical region edited")
    seed_used: int = Field(..., description="RNG seed used for the operation")
    prompt_used: str = Field(..., description="Prompt generated for the inpainting operation")
    attr_adherence: Optional[float] = Field(None, description="Optional attribute adherence score in [0, 1]")


@router.post(
    "/edit",
    response_model=EditResponse,
    summary="Inpaint / Edit Specific Facial Region",
    dependencies=[Depends(verify_service_key)],
)
async def edit_facial_region(req: EditRequest) -> EditResponse:
    """Performs localized facial region editing using feathered masking and sketch inpainting."""
    t0 = time.perf_counter()
    logger.info("Received facial edit request: region=%s, seed=%d", req.region, req.seed)

    # 1. Resolve source image
    source_img = resolve_image_from_request(req.image_b64, req.image_id)
    width, height = source_img.size

    # 2. Resolve or generate region mask
    if req.mask_b64:
        mask_img = decode_base64_image(req.mask_b64).convert("L")
        if mask_img.size != (width, height):
            mask_img = mask_img.resize((width, height), Image.Resampling.BILINEAR)
    else:
        mask_img = region_masker.generate_region_mask(
            region=req.region,
            image_size=(width, height),
            feather_radius=req.feather_radius,
        )

    # 3. Construct prompt
    if req.updated_attributes:
        prompt_text = build_facial_composite_prompt(req.updated_attributes)
    else:
        prompt_text = f"{SKETCH_BASE_STYLE_POSITIVE}, forensic facial modification of {req.region or 'feature'}, {req.edit_instruction}"

    # 4. Execute inpainting / regional synthesis
    try:
        # Load generative pipeline
        pipe = model_manager.load_pipeline(
            model_id=settings.DEFAULT_MODEL_ID,
            vae_id=settings.DEFAULT_VAE_ID,
            lcm_lora_id=settings.DEFAULT_LCM_LORA_ID,
        )

        use_cpu_generator = model_manager.low_vram_mode or "cuda" not in model_manager.device
        generator = torch.Generator(device="cpu" if use_cpu_generator else "cuda").manual_seed(req.seed)

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        # Render replacement variant
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

        generated_patch = res.images[0]

        # Composite the newly generated patch onto the source image through the feathered mask
        # Mask: 255 = inpaint (use generated_patch), 0 = preserve (use source_img)
        final_img = Image.composite(generated_patch, source_img, mask_img)

    except Exception as e:
        logger.error("Edit generation failed: %s", str(e), exc_info=True)
        raise MLError(
            code="INTERNAL",
            message=f"Failed to execute facial region inpainting: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"error_type": type(e).__name__},
        )

    dt = time.perf_counter() - t0
    logger.info("Facial edit completed in %.2fs: region=%s", dt, req.region)

    # Compute attribute adherence on edited image if updated attributes were provided
    edit_adherence: Optional[float] = None
    if req.updated_attributes:
        candidate_attrs = [k for k in req.updated_attributes.keys() if k in ATTRIBUTE_ENUM_REGISTRY]
        if candidate_attrs:
            try:
                v_res = attribute_verifier.verify_attributes(
                    image=final_img,
                    requested_attributes=candidate_attrs,
                    stated_attributes=req.updated_attributes,
                )
                edit_adherence = v_res.get("attr_adherence")
            except Exception as ve:
                logger.warning("Could not calculate attribute adherence for edit: %s", str(ve))

    return EditResponse(
        status="ok",
        image_base64=encode_image_to_base64_uri(final_img),
        mask_used_base64=encode_image_to_base64_uri(mask_img.convert("RGB")),
        region=req.region,
        seed_used=req.seed,
        prompt_used=prompt_text,
        attr_adherence=edit_adherence,
    )
