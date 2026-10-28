"""
ArcFace face embedder interface and pipeline for Velora ML Service.
Adheres to:
- MASTER_PROMPT.md §11 Step A3 requirements (512-dim L2-normalized vector)
- contracts/schema.sql (gallery_faces role: 'face_embedder')
- Strict safety rules: returns explicit ML_UNAVAILABLE error when weights are not loaded,
  never fabricating vectors or substituting unapproved models.
"""

import logging
from typing import Any, Dict, List, Optional
import numpy as np
from PIL import Image

from ml_service.app.core.errors import MLError

logger = logging.getLogger("velora.ml.face_embedder")


class FaceNotDetectedError(MLError):
    """Raised when no face is localized in the input image."""

    def __init__(self, message: str = "No face detected in the provided image"):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details={"face_detected": False},
        )


class FaceEmbedder:
    """ArcFace face embedding pipeline producing 512-dimensional L2-normalized vectors."""

    def __init__(self, model_version: str = "arcface-r100-v1"):
        self.model_version = model_version
        self._model = None
        self._detector = None
        self._weights_loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        """Returns True only when real ArcFace weights are loaded and verified."""
        return self._weights_loaded

    def load_model(self) -> None:
        """
        Attempts to load ArcFace weights.
        If weights are not available locally, raises MLError(code='ML_UNAVAILABLE').
        """
        if self._weights_loaded:
            return

        # Explicit check: Zero unapproved downloads or mock substitutions
        logger.warning(
            "ArcFace model weights (%s) are not currently loaded on disk. "
            "Awaiting explicit licensing review and human download authorization.",
            self.model_version,
        )
        raise MLError(
            code="ML_UNAVAILABLE",
            message=(
                f"ArcFace model weights ({self.model_version}) are not loaded. "
                "Pretrained checkpoint download is pending licensing review and explicit human authorization."
            ),
            status_code=503,
            details={
                "model_version": self.model_version,
                "weights_loaded": False,
                "licensing_status": "pending_human_review",
            },
        )

    def extract_embedding(self, image: Image.Image) -> Dict[str, Any]:
        """
        Extracts 512-dimensional L2-normalized facial embedding from a PIL Image.
        Raises ML_UNAVAILABLE if weights are not loaded.
        Raises VALIDATION_ERROR (422) if no face is detected.
        """
        if not self._weights_loaded:
            self.load_model()

        # When real weights are present, inference executes here
        # Face detection -> alignment -> ArcFace forward -> L2 normalization
        raise NotImplementedError("Real inference requires loaded ArcFace weights.")


# Global singleton instance
face_embedder = FaceEmbedder(model_version="arcface-r100-v1")
