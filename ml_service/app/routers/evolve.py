"""
Evolutionary Preference Grid synthesis endpoint for Velora ML Service.
Endpoint: POST /ml/v1/evolve
Adheres to:
- MASTER_PROMPT.md §1 D1 (Recognition-first variant grid with online preference model)
- MASTER_PROMPT.md §11 Step A5
- Standardized error and auth contracts (§6.3)
"""

import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from PIL import Image
import torch

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.models.manager import model_manager
from ml_service.app.pipelines.sketch_prompts import (
    SKETCH_NEGATIVE_PROMPT,
    build_facial_composite_prompt,
)
from ml_service.app.preference.preference_model import preference_model
from ml_service.app.routers.generate import encode_image_to_base64_uri

logger = logging.getLogger("velora.ml.evolve")
router = APIRouter(tags=["evolve"])


class EvolvedVariantItem(BaseModel):
    """Metadata and image payload for one evolved grid variant."""

    variant_index: int = Field(..., description="0-indexed variant position in grid (0 to N-1)")
    seed: int = Field(..., description="RNG seed used for this variant")
    image_base64: str = Field(..., description="Generated sketch variant as PNG base64 data URI")
    variant_axes: Dict[str, float] = Field(..., description="Axis offset values applied to this variant")
    prompt_used: str = Field(..., description="Full prompt text used for synthesis")


class EvolveRequest(BaseModel):
    """Request payload for multi-round witness preference evolution."""

    session_id: str = Field(..., description="Forensic interview session UUID")
    case_id: Optional[str] = Field(None, description="Associated case UUID")
    round_number: int = Field(1, ge=1, description="1-indexed current interview round")
    base_attributes: Dict[str, Any] = Field(..., description="Stated facial attributes dictionary")
    feedback_events: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, description="Witness feedback events from prior round"
    )
    current_preference_vector: Optional[Dict[str, float]] = Field(
        None, description="Existing preference vector from preceding round"
    )
    num_variants: int = Field(6, ge=2, le=12, description="Number of variants to render in this round (default 6)")
    seed: int = Field(42, description="Base seed for reproducibility")
    image_size: int = Field(512, ge=64, le=1024, description="Square pixel resolution")


class EvolveResponse(BaseModel):
    """Response payload for multi-round witness preference evolution."""

    status: str = Field("ok", description="Status code string")
    session_id: str = Field(..., description="Forensic interview session UUID")
    round_number: int = Field(..., description="Current interview round index")
    preference_vector: Dict[str, float] = Field(..., description="Updated explainable preference state vector")
    variants: List[EvolvedVariantItem] = Field(..., description="Rendered variant grid items")


@router.post(
    "/evolve",
    response_model=EvolveResponse,
    summary="Synthesize Evolutionary Variant Grid with Online Preference Learning",
    dependencies=[Depends(verify_service_key)],
)
async def evolve_variant_grid(req: EvolveRequest) -> EvolveResponse:
    """
    Executes recognition-first evolutionary variant generation:
    1. Updates continuous preference vector from witness feedback.
    2. Samples N variant axes with round-decaying variance.
    3. Synthesizes monochrome facial sketches along sampled axes.
    """
    t0 = time.perf_counter()
    logger.info(
        "Received evolve request: session=%s, round=%d, feedback_count=%d",
        req.session_id,
        req.round_number,
        len(req.feedback_events or []),
    )

    # 1. Update preference state vector
    prev_vector = req.current_preference_vector or preference_model.init_preference_vector()
    updated_vector = preference_model.update_preference_vector(
        current_vector=prev_vector,
        feedback_events=req.feedback_events or [],
    )

    # 2. Sample variant parameter axes
    sampled_axes_list = preference_model.sample_round_variants(
        preference_vector=updated_vector,
        round_number=req.round_number,
        num_variants=req.num_variants,
        seed=req.seed,
    )

    # 3. Build prompts for each variant
    base_prompt = build_facial_composite_prompt(req.base_attributes)
    variant_tasks: List[Dict[str, Any]] = []

    for idx, axes in enumerate(sampled_axes_list):
        modifiers = preference_model.build_variant_prompt_modifiers(axes)
        prompt_with_axes = base_prompt
        if modifiers:
            prompt_with_axes = f"{base_prompt}, {', '.join(modifiers)}"

        item_seed = req.seed + (idx * 1013)
        variant_tasks.append({
            "variant_index": idx,
            "seed": item_seed,
            "prompt": prompt_with_axes,
            "variant_axes": axes,
        })

    # 4. Synthesize sketch variants
    variants_out: List[EvolvedVariantItem] = []
    try:
        pipe = model_manager.load_pipeline(
            model_id=settings.DEFAULT_MODEL_ID,
            vae_id=settings.DEFAULT_VAE_ID,
            lcm_lora_id=settings.DEFAULT_LCM_LORA_ID,
        )

        use_cpu_generator = model_manager.low_vram_mode or "cuda" not in model_manager.device

        for task in variant_tasks:
            generator = torch.Generator(device="cpu" if use_cpu_generator else "cuda").manual_seed(task["seed"])

            if torch.cuda.is_available():
                torch.cuda.synchronize()

            res = pipe(
                prompt=task["prompt"],
                negative_prompt=SKETCH_NEGATIVE_PROMPT,
                width=req.image_size,
                height=req.image_size,
                num_inference_steps=settings.ML_VARIANT_STEPS,
                guidance_scale=1.5,
                generator=generator,
            )

            if torch.cuda.is_available():
                torch.cuda.synchronize()

            pil_img = res.images[0]
            b64_uri = encode_image_to_base64_uri(pil_img)

            variants_out.append(
                EvolvedVariantItem(
                    variant_index=task["variant_index"],
                    seed=task["seed"],
                    image_base64=b64_uri,
                    variant_axes=task["variant_axes"],
                    prompt_used=task["prompt"],
                )
            )

    except Exception as e:
        logger.error("Variant evolution failed: %s", str(e), exc_info=True)
        raise MLError(
            code="INTERNAL",
            message=f"Failed to synthesize evolutionary variants: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"error_type": type(e).__name__},
        )

    dt = time.perf_counter() - t0
    logger.info("Evolution round %d completed in %.2fs (rendered %d variants)", req.round_number, dt, len(variants_out))

    return EvolveResponse(
        status="ok",
        session_id=req.session_id,
        round_number=req.round_number,
        preference_vector=updated_vector,
        variants=variants_out,
    )
