"""
Verification and embedding endpoints for Velora ML Service.
Endpoints:
- POST /ml/v1/verify-attributes: CLIP zero-shot facial attribute scoring and adherence
- POST /ml/v1/embed: ArcFace 512-dimensional L2-normalized face embedding

Enforces:
- Service authentication (X-Service-Key)
- Strict request and response schemas matching contracts/schema.sql and contracts/face_attributes.schema.json
- Standardized error schema (§6.3)
"""

import base64
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator
from PIL import Image

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.core.errors import MLError
from ml_service.app.pipelines.attribute_verifier import attribute_verifier
from ml_service.app.pipelines.face_embedder import face_embedder

logger = logging.getLogger("velora.ml.verify_router")
router = APIRouter(tags=["verify"])


def decode_base64_image(image_b64: str) -> Image.Image:
    """Decodes a base64 image string (with or without data URI header) into a PIL Image."""
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes))
        img.verify()
        # Re-open after verify() per PIL specifications
        img = Image.open(io.BytesIO(img_bytes))
        return img.convert("RGB")
    except Exception as e:
        logger.warning("Failed to decode base64 image: %s", str(e))
        raise MLError(
            code="VALIDATION_ERROR",
            message="Invalid base64 image payload",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"error": type(e).__name__},
        )


def resolve_image_from_request(image_b64: Optional[str], image_id: Optional[str]) -> Image.Image:
    """
    Resolves a PIL Image from either base64 payload or disk storage via image_id.
    Adheres strictly to contracts/schema.sql storage conventions.
    """
    if image_b64:
        return decode_base64_image(image_b64)

    if image_id:
        clean_id = Path(image_id).name  # Prevent directory traversal attacks
        candidate_paths = [
            settings.ML_STORAGE_DIR / clean_id,
            settings.ML_STORAGE_DIR / f"{clean_id}.png",
            settings.ML_STORAGE_DIR / f"{clean_id}.jpg",
            settings.REPO_ROOT / "backend" / "storage" / "images" / clean_id,
            settings.REPO_ROOT / "backend" / "storage" / "images" / f"{clean_id}.png",
            settings.REPO_ROOT / "backend" / "storage" / "images" / f"{clean_id}.jpg",
        ]
        for p in candidate_paths:
            if p.exists() and p.is_file():
                try:
                    img = Image.open(p)
                    return img.convert("RGB")
                except Exception as e:
                    logger.warning("Corrupt image file at %s: %s", p, str(e))
                    raise MLError(
                        code="VALIDATION_ERROR",
                        message=f"Corrupt image file stored for image_id '{clean_id}'",
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )

        raise MLError(
            code="NOT_FOUND",
            message=f"Image for image_id '{clean_id}' not found in storage",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    raise MLError(
        code="VALIDATION_ERROR",
        message="At least one of image_b64 or image_id must be provided",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


# ============================================================================
# 1. Attribute Verification Models & Endpoint
# ============================================================================
class VerifyAttributesRequest(BaseModel):
    """Request payload for zero-shot attribute verification."""

    image_b64: Optional[str] = Field(None, description="Base64 encoded image string or PNG data URI")
    image_id: Optional[str] = Field(None, description="Optional associated image UUID")
    requested_attributes: List[str] = Field(
        ..., min_length=1, description="List of attribute names to probe against face_attributes schema"
    )
    stated_attributes: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Attributes explicitly stated by witness"
    )

    @model_validator(mode="after")
    def validate_image_source(self) -> "VerifyAttributesRequest":
        if not self.image_b64 and not self.image_id:
            raise ValueError("At least one of image_b64 or image_id must be provided")
        return self


class VerifyAttributesResponse(BaseModel):
    """Response payload for zero-shot attribute verification."""

    status: str = Field("ok", description="Status code string")
    image_id: Optional[str] = Field(None, description="Associated image UUID")
    attribute_scores: Dict[str, Dict[str, float]] = Field(
        ..., description="Normalized softmax probabilities across valid enum choices per requested attribute"
    )
    stated_probabilities: Dict[str, float] = Field(
        ..., description="Probability assigned to each stated attribute value"
    )
    attr_adherence: Optional[float] = Field(
        None, description="Mean probability across stated attributes in [0, 1]; None if no stated attributes"
    )


@router.post(
    "/verify-attributes",
    response_model=VerifyAttributesResponse,
    summary="Zero-shot Attribute Verification via CLIP",
    dependencies=[Depends(verify_service_key)],
)
async def verify_attributes(req: VerifyAttributesRequest) -> VerifyAttributesResponse:
    """Evaluates an image against specified facial attributes and computes attr_adherence."""
    logger.info(
        "Received verify-attributes request: requested_count=%d, stated_count=%d",
        len(req.requested_attributes),
        len(req.stated_attributes or {}),
    )

    image = resolve_image_from_request(req.image_b64, req.image_id)
    results = attribute_verifier.verify_attributes(
        image=image,
        requested_attributes=req.requested_attributes,
        stated_attributes=req.stated_attributes,
    )

    return VerifyAttributesResponse(
        status="ok",
        image_id=req.image_id,
        attribute_scores=results["attribute_scores"],
        stated_probabilities=results["stated_probabilities"],
        attr_adherence=results["attr_adherence"],
    )


# ============================================================================
# 2. Face Embedding Models & Endpoint
# ============================================================================
class EmbedRequest(BaseModel):
    """Request payload for ArcFace face embedding extraction."""

    image_b64: Optional[str] = Field(None, description="Base64 encoded image string or PNG data URI")
    image_id: Optional[str] = Field(None, description="Optional associated image UUID")

    @model_validator(mode="after")
    def validate_image_source(self) -> "EmbedRequest":
        if not self.image_b64 and not self.image_id:
            raise ValueError("At least one of image_b64 or image_id must be provided")
        return self


class EmbedResponse(BaseModel):
    """Response payload for ArcFace face embedding extraction."""

    status: str = Field("ok", description="Status code string")
    image_id: Optional[str] = Field(None, description="Associated image UUID")
    embedding: List[float] = Field(..., description="512-dimensional float32 L2-normalized embedding vector")
    embedding_l2_norm: float = Field(..., description="L2 norm of embedding vector, strictly 1.0 ± 1e-3")
    model_version: str = Field(..., description="Model version tag per contracts/schema.sql")
    face_detected: bool = Field(True, description="Whether a face was localized")
    bounding_box: Optional[Dict[str, int]] = Field(None, description="Bounding box [x1, y1, x2, y2]")
    det_score: Optional[float] = Field(None, description="Face detector confidence score")


@router.post(
    "/embed",
    response_model=EmbedResponse,
    summary="Extract ArcFace 512-dimensional Face Embedding",
    dependencies=[Depends(verify_service_key)],
)
async def extract_face_embedding(req: EmbedRequest) -> EmbedResponse:
    """Extracts a 512-dimensional L2-normalized ArcFace embedding vector from an input face image."""
    logger.info("Received embed request: image_id=%s", req.image_id)

    image = resolve_image_from_request(req.image_b64, req.image_id)
    result = face_embedder.extract_embedding(image)

    return EmbedResponse(
        status="ok",
        image_id=req.image_id,
        embedding=result["embedding"],
        embedding_l2_norm=result["embedding_l2_norm"],
        model_version=result["model_version"],
        face_detected=result["face_detected"],
        bounding_box=result.get("bounding_box"),
        det_score=result.get("det_score"),
    )
