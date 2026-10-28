"""
Portrait Finalization and Export Preparation router for Velora ML Service.
Endpoint: POST /ml/v1/finalize
Adheres to:
- MASTER_PROMPT.md §0 R11 Invariant 3 (Mandatory investigative aid disclaimer)
- MASTER_PROMPT.md §11 Step A6 (Upscale / finalize)
- contracts/schema.sql sha256 integrity hashing
"""

import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator
from PIL import Image

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.pipelines.upscaler import portrait_finalizer
from ml_service.app.routers.generate import encode_image_to_base64_uri
from ml_service.app.routers.verify import resolve_image_from_request

logger = logging.getLogger("velora.ml.finalize")
router = APIRouter(tags=["finalize"])


class FinalizeRequest(BaseModel):
    """Request payload for portrait upscaling, contrast enhancement, and watermark stamping."""

    image_b64: Optional[str] = Field(None, description="Base64 encoded source image string or data URI")
    image_id: Optional[str] = Field(None, description="Optional associated image UUID")
    scale_factor: int = Field(2, description="Upscale multiplier (1, 2, or 4)")
    apply_watermark: bool = Field(True, description="Whether to stamp mandatory R11 investigative aid disclaimer")
    enhance_contrast: bool = Field(True, description="Whether to apply subtle pencil line sharpening and contrast boost")

    @model_validator(mode="after")
    def validate_source(self) -> "FinalizeRequest":
        if not self.image_b64 and not self.image_id:
            raise ValueError("At least one of image_b64 or image_id must be provided")
        if self.scale_factor not in (1, 2, 4):
            raise ValueError(f"Scale factor must be 1, 2, or 4; received {self.scale_factor}")
        return self


class FinalizeResponse(BaseModel):
    """Response payload for portrait finalization."""

    status: str = Field("ok", description="Status code string")
    image_base64: str = Field(..., description="Finalized sketch as PNG base64 data URI")
    original_width: int = Field(..., description="Source width in pixels")
    original_height: int = Field(..., description="Source height in pixels")
    final_width: int = Field(..., description="Final output width in pixels")
    final_height: int = Field(..., description="Final output height in pixels")
    scale_factor: int = Field(..., description="Applied scale multiplier")
    sha256: str = Field(..., description="SHA256 hex digest of the finalized image PNG bytes")
    disclaimer: str = Field(..., description="Text of the responsible AI disclaimer stamped on the image")


@router.post(
    "/finalize",
    response_model=FinalizeResponse,
    summary="Upscale, Enhance Contrast, and Watermark Suspect Composite",
    dependencies=[Depends(verify_service_key)],
)
async def finalize_suspect_portrait(req: FinalizeRequest) -> FinalizeResponse:
    """Produces the final high-resolution, watermarked, cryptographically hashed suspect composite."""
    t0 = time.perf_counter()
    logger.info("Received finalize request: scale=%d, watermark=%s", req.scale_factor, req.apply_watermark)

    # 1. Resolve source image
    source_img = resolve_image_from_request(req.image_b64, req.image_id)
    orig_w, orig_h = source_img.size

    # 2. Upscale and enhance
    upscaled = portrait_finalizer.upscale_image(
        image=source_img,
        scale_factor=req.scale_factor,
        enhance_contrast=req.enhance_contrast,
    )

    # 3. Apply watermark if requested
    if req.apply_watermark:
        final_img = portrait_finalizer.apply_disclaimer_watermark(upscaled)
    else:
        final_img = upscaled

    final_w, final_h = final_img.size

    # 4. Compute cryptographic integrity hash
    sha256_hex = portrait_finalizer.compute_sha256(final_img)
    b64_uri = encode_image_to_base64_uri(final_img)

    dt = time.perf_counter() - t0
    logger.info("Portrait finalization completed in %.2fs: %dx%d -> %dx%d", dt, orig_w, orig_h, final_w, final_h)

    return FinalizeResponse(
        status="ok",
        image_base64=b64_uri,
        original_width=orig_w,
        original_height=orig_h,
        final_width=final_w,
        final_height=final_h,
        scale_factor=req.scale_factor,
        sha256=sha256_hex,
        disclaimer=settings.DISCLAIMER_V1,
    )
