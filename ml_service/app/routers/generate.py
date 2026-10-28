"""
Generation endpoint for Velora ML Service.
Endpoint: POST /ml/v1/generate

Supports:
- Option A: Facial Composite Sketch (from structured witness descriptors)
- Option B: Incident Storyboard Sketches (from ordered event narratives)

Enforces:
- Service-to-service auth (X-Service-Key)
- ModelManager VRAM discipline and sequential offloading
- Disclaimer injection
- Standardized error schema (§6.3)
"""

import base64
import io
import logging
import time
from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator
import torch
from PIL import Image

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.models.manager import model_manager
from ml_service.app.pipelines.attribute_verifier import ATTRIBUTE_ENUM_REGISTRY, attribute_verifier
from ml_service.app.pipelines.sketch_prompts import (
    SKETCH_NEGATIVE_PROMPT,
    build_facial_composite_prompt,
    build_storyboard_frame_prompt,
)

logger = logging.getLogger("velora.ml.generate")
router = APIRouter(tags=["generate"])


class StoryboardEvent(BaseModel):
    """Structured representation of a single incident narrative event."""

    frame_index: int = Field(..., ge=1, le=10, description="Sequential position in incident")
    description: str = Field(..., min_length=3, max_length=500, description="Event action and subject description")
    action: Optional[str] = Field(None, max_length=150, description="Primary verb or interaction")
    characters: Optional[List[str]] = Field(default_factory=list, description="Described people involved")
    objects: Optional[List[str]] = Field(default_factory=list, description="Relevant objects/items")
    location: Optional[str] = Field(None, max_length=150, description="Setting or environmental backdrop")
    is_uncertain: bool = Field(False, description="Flag indicating speculative or assumed detail")


class GenerateRequest(BaseModel):
    """Request payload for suspect composite or incident sketch generation."""

    module_type: Literal["facial_composite", "incident_storyboard"] = Field(
        ..., description="Target generation mode"
    )
    case_id: Optional[str] = Field(None, description="Associated case UUID")
    seed: int = Field(42, description="Base random seed for deterministic generation")
    num_variants: int = Field(1, ge=1, le=6, description="Number of variants to generate (facial composite only)")
    image_size: int = Field(512, ge=256, le=512, description="Target square image resolution")
    num_inference_steps: int = Field(3, ge=1, le=10, description="LCM scheduler inference steps")
    guidance_scale: float = Field(1.5, ge=1.0, le=5.0, description="CFG guidance scale")

    # Module-specific payloads
    facial_attributes: Optional[Dict[str, Any]] = Field(
        None, description="Witness-described facial features (required for facial_composite)"
    )
    storyboard_events: Optional[List[StoryboardEvent]] = Field(
        None, description="Ordered event frames (required for incident_storyboard, max 6 frames)"
    )

    @model_validator(mode="after")
    def validate_module_payloads(self) -> "GenerateRequest":
        if self.module_type == "facial_composite" and not self.facial_attributes:
            raise ValueError("facial_attributes must be provided for module_type='facial_composite'")
        if self.module_type == "incident_storyboard":
            if not self.storyboard_events or len(self.storyboard_events) == 0:
                raise ValueError("At least one event frame must be provided for module_type='incident_storyboard'")
            if len(self.storyboard_events) > 6:
                raise ValueError("Maximum 6 storyboard frames allowed per generation batch")
        return self


class GeneratedImageItem(BaseModel):
    """Output descriptor for an individual generated sketch."""

    index: int = Field(..., description="Zero-based output index or frame index")
    seed: int = Field(..., description="Random seed used for generation")
    image_base64: str = Field(..., description="PNG data URI (data:image/png;base64,...)")
    prompt_used: str = Field(..., description="Full synthesized prompt string")
    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")
    label: str = Field(..., description="Descriptive identifier for the output item")
    is_uncertain: bool = Field(False, description="Whether detail contains marked speculative assumptions")
    attr_adherence: Optional[float] = Field(None, description="Zero-shot CLIP adherence score of stated attributes in [0, 1]")


class GenerateResponse(BaseModel):
    """Response payload for sketch generation."""

    status: str = Field("ok", description="Status code string")
    module_type: str = Field(..., description="Executed generation module")
    case_id: Optional[str] = Field(None, description="Case identifier")
    disclaimer: str = Field(..., description="Mandatory responsible AI disclaimer")
    count: int = Field(..., description="Number of generated sketches")
    images: List[GeneratedImageItem] = Field(..., description="List of generated sketch items")
    latency_sec: float = Field(..., description="Total wall-clock generation time in seconds")
    peak_vram_mb: float = Field(..., description="Peak allocated GPU memory in MiB")


def encode_image_to_base64_uri(image: Image.Image) -> str:
    """Encodes a PIL Image to a base64 PNG data URI."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


@router.post(
    "/generate",
    response_model=GenerateResponse,
    summary="Generate Suspect Composites or Incident Storyboards",
    dependencies=[Depends(verify_service_key)],
)
async def generate_sketches(req: GenerateRequest) -> GenerateResponse:
    """
    Executes illustrative monochrome sketch generation:
    - Option A (facial_composite): renders N variants with seed progression.
    - Option B (incident_storyboard): renders sequential event frames.
    """
    t0 = time.perf_counter()
    logger.info("Received sketch generation request: module=%s, case=%s", req.module_type, req.case_id)

    # 1. Load / access generative pipeline through ModelManager
    try:
        pipe = model_manager.load_pipeline(
            model_id=settings.DEFAULT_MODEL_ID,
            vae_id=settings.DEFAULT_VAE_ID,
            lcm_lora_id=settings.DEFAULT_LCM_LORA_ID,
        )
    except Exception as e:
        logger.error("Failed to load generation pipeline: %s", str(e), exc_info=True)
        raise MLError(
            code="ML_UNAVAILABLE",
            message="Image generation pipeline failed to load into memory",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"error_type": type(e).__name__},
        )

    # 2. Build task prompts and metadata
    tasks: List[Dict[str, Any]] = []

    if req.module_type == "facial_composite":
        prompt_text = build_facial_composite_prompt(req.facial_attributes or {})
        for idx in range(req.num_variants):
            item_seed = req.seed + (idx * 997)
            tasks.append({
                "index": idx,
                "seed": item_seed,
                "prompt": prompt_text,
                "label": f"variant_{idx + 1}",
                "is_uncertain": False,
            })

    elif req.module_type == "incident_storyboard":
        sorted_events = sorted(req.storyboard_events or [], key=lambda e: e.frame_index)
        for idx, evt in enumerate(sorted_events):
            prompt_text = build_storyboard_frame_prompt(
                event_description=evt.description,
                action=evt.action,
                characters=evt.characters,
                objects=evt.objects,
                location=evt.location,
                is_uncertain=evt.is_uncertain,
            )
            item_seed = req.seed + (idx * 503)
            tasks.append({
                "index": evt.frame_index,
                "seed": item_seed,
                "prompt": prompt_text,
                "label": f"frame_{evt.frame_index}",
                "is_uncertain": evt.is_uncertain,
            })

    # 3. Execute sequential inference loop
    generated_items: List[GeneratedImageItem] = []
    use_cpu_generator = model_manager.low_vram_mode or "cuda" not in model_manager.device

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    try:
        for t in tasks:
            generator = torch.Generator(device="cpu" if use_cpu_generator else "cuda").manual_seed(t["seed"])

            if torch.cuda.is_available():
                torch.cuda.synchronize()

            res = pipe(
                prompt=t["prompt"],
                negative_prompt=SKETCH_NEGATIVE_PROMPT,
                width=req.image_size,
                height=req.image_size,
                num_inference_steps=req.num_inference_steps,
                guidance_scale=req.guidance_scale,
                generator=generator,
            )

            if torch.cuda.is_available():
                torch.cuda.synchronize()

            pil_img = res.images[0]
            b64_uri = encode_image_to_base64_uri(pil_img)

            # Compute zero-shot CLIP attribute adherence for facial composite sketches
            item_adherence: Optional[float] = None
            if req.module_type == "facial_composite" and req.facial_attributes:
                candidate_attrs = [k for k in req.facial_attributes.keys() if k in ATTRIBUTE_ENUM_REGISTRY]
                if candidate_attrs:
                    try:
                        v_res = attribute_verifier.verify_attributes(
                            image=pil_img,
                            requested_attributes=candidate_attrs,
                            stated_attributes=req.facial_attributes,
                        )
                        item_adherence = v_res.get("attr_adherence")
                    except Exception as ve:
                        logger.warning("Could not calculate attribute adherence for item %d: %s", t["index"], str(ve))

            generated_items.append(
                GeneratedImageItem(
                    index=t["index"],
                    seed=t["seed"],
                    image_base64=b64_uri,
                    prompt_used=t["prompt"],
                    width=pil_img.width,
                    height=pil_img.height,
                    label=t["label"],
                    is_uncertain=t["is_uncertain"],
                    attr_adherence=item_adherence,
                )
            )
    except Exception as e:
        logger.error("Generation execution error: %s", str(e), exc_info=True)
        raise MLError(
            code="INTERNAL",
            message="An error occurred while generating sketch frames",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"error_type": type(e).__name__},
        )

    dt = time.perf_counter() - t0
    peak_vram = 0.0
    if torch.cuda.is_available() and "cuda" in model_manager.device:
        peak_vram = round(torch.cuda.max_memory_allocated() / (1024**2), 1)

    # Proactively release intermediate activation memory to prevent fragmentation
    model_manager.clean_vram_cache()

    logger.info(
        "Successfully generated %d sketch(es) for case=%s in %.2fs (Peak VRAM: %.1f MiB)",
        len(generated_items),
        req.case_id or "N/A",
        dt,
        peak_vram,
    )

    return GenerateResponse(
        status="ok",
        module_type=req.module_type,
        case_id=req.case_id,
        disclaimer=settings.DISCLAIMER_V1,
        count=len(generated_items),
        images=generated_items,
        latency_sec=round(dt, 3),
        peak_vram_mb=peak_vram,
    )
