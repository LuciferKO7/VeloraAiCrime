"""
Forensic Image Transformation Engine for Velora ML Service.
Adheres to:
- MASTER_PROMPT.md §1 D7 (Transforms: age progression/regression, disguise removal, side profile)
- MASTER_PROMPT.md §11 Step A7
- contracts/schema.sql kind enum ('age', 'disguise', 'profile') and speculative flag
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from ml_service.app.masks.region_masker import region_masker

logger = logging.getLogger("velora.ml.transforms")

SKETCH_BASE_STYLE_POSITIVE: str = "forensic pencil sketch, monochrome graphite drawing on paper"

SUPPORTED_TRANSFORM_KINDS: List[str] = [
    "age_progression",
    "age_regression",
    "disguise_removal",
    "side_profile",
]

DISGUISE_TARGETS: List[str] = [
    "glasses",
    "headwear",
    "facial_hair",
]


class ForensicTransformEngine:
    """Orchestrates forensic transformations with specialized prompt templates and region targeting."""

    def __init__(self):
        self.supported_transforms = list(SUPPORTED_TRANSFORM_KINDS)

    def get_supported_transforms(self) -> List[str]:
        return self.supported_transforms

    def build_transform_prompt(
        self,
        transform_kind: str,
        base_description: Optional[str] = None,
        target_disguise: Optional[str] = None,
        age_delta_years: int = 20,
    ) -> Tuple[str, str, bool]:
        """
        Builds transformation positive prompt, target anatomical region, and speculative flag.
        Returns (prompt_text, target_region, is_speculative).
        """
        kind_clean = transform_kind.strip().lower()
        base_desc = base_description or "monochrome pencil portrait of suspect"

        if kind_clean == "age_progression":
            prompt = (
                f"forensic pencil sketch, aged mature suspect composite, approximately {age_delta_years} years older, "
                f"mature skin texture with subtle fine character lines, natural facial aging, {base_desc}"
            )
            return prompt, "cheeks", True

        if kind_clean == "age_regression":
            prompt = (
                f"forensic pencil sketch, youthful suspect composite, approximately {age_delta_years} years younger, "
                f"smooth skin, taut youthful jawline, clean firm contours, {base_desc}"
            )
            return prompt, "cheeks", True

        if kind_clean == "disguise_removal":
            target = (target_disguise or "all").lower()
            if target == "glasses":
                prompt = (
                    f"forensic pencil sketch, disguise removal without eyeglasses, clean uncovered eyes, "
                    f"natural eye contours and bridge, {base_desc}"
                )
                return prompt, "eyes", True
            elif target == "headwear":
                prompt = (
                    f"forensic pencil sketch, disguise removal without hat cap or headwear, natural visible hairline, "
                    f"uncovered forehead, {base_desc}"
                )
                return prompt, "hair", True
            elif target == "facial_hair":
                prompt = (
                    f"forensic pencil sketch, clean shaven suspect portrait without beard or mustache, "
                    f"visible clean chin and jaw, {base_desc}"
                )
                return prompt, "mouth", True
            else:
                prompt = (
                    f"forensic pencil sketch, complete disguise removal, clean uncovered face without glasses or hat, "
                    f"clean-shaven, unobstructed facial features, {base_desc}"
                )
                return prompt, "cheeks", True

        if kind_clean == "side_profile":
            prompt = (
                f"forensic pencil sketch, exact 90-degree lateral side profile perspective, anatomical ear and nose silhouette, "
                f"monochrome graphite profile drawing on paper, {base_desc}"
            )
            return prompt, "hair", True

        raise ValueError(
            f"Unsupported transform kind '{transform_kind}'. Supported: {', '.join(SUPPORTED_TRANSFORM_KINDS)}"
        )


transform_engine = ForensicTransformEngine()
