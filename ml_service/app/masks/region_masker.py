"""
Facial Region Mask Generator for Velora ML Service.
Adheres to:
- MASTER_PROMPT.md §11 Step A4 (Region masks and /edit)
- 8 canonical anatomical regions: hair, eyes, eyebrows, nose, mouth, jaw, cheeks, forehead
- Generates clean binary alpha masks with feathering for seamless inpainting blending.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger("velora.ml.region_masker")

CANONICAL_REGIONS: List[str] = [
    "hair",
    "forehead",
    "eyebrows",
    "eyes",
    "nose",
    "cheeks",
    "mouth",
    "jaw",
]

# Proportional anatomical bounds for centered 512x512 portrait sketches
# Values represent [ymin, xmin, ymax, xmax] as fractions of image dimensions [0.0, 1.0]
PROPORTIONAL_REGION_BOUNDS: Dict[str, List[float]] = {
    "hair": [0.00, 0.10, 0.38, 0.90],
    "forehead": [0.18, 0.25, 0.36, 0.75],
    "eyebrows": [0.30, 0.22, 0.40, 0.78],
    "eyes": [0.34, 0.22, 0.46, 0.78],
    "nose": [0.42, 0.38, 0.62, 0.62],
    "cheeks": [0.44, 0.18, 0.68, 0.82],
    "mouth": [0.60, 0.32, 0.78, 0.68],
    "jaw": [0.68, 0.22, 0.95, 0.78],
}


class FacialRegionMasker:
    """Generates precise, feathered region masks for localized inpainting edits."""

    def __init__(self, default_size: Tuple[int, int] = (512, 512)):
        self.default_size = default_size

    def get_supported_regions(self) -> List[str]:
        """Returns the list of supported canonical facial regions."""
        return list(CANONICAL_REGIONS)

    def generate_region_mask(
        self,
        region: str,
        image_size: Optional[Tuple[int, int]] = None,
        feather_radius: int = 8,
    ) -> Image.Image:
        """
        Generates a grayscale mask (255=inpaint, 0=preserve) for a requested anatomical region.
        Applies Gaussian feathering to prevent hard seams during blending.
        """
        reg_clean = region.strip().lower()
        if reg_clean not in PROPORTIONAL_REGION_BOUNDS:
            raise ValueError(
                f"Unsupported facial region '{region}'. Supported regions: {', '.join(CANONICAL_REGIONS)}"
            )

        width, height = image_size or self.default_size
        mask = Image.new("L", (width, height), color=0)
        draw = ImageDraw.Draw(mask)

        ymin, xmin, ymax, xmax = PROPORTIONAL_REGION_BOUNDS[reg_clean]
        x1 = int(xmin * width)
        y1 = int(ymin * height)
        x2 = int(xmax * width)
        y2 = int(ymax * height)

        if reg_clean == "hair":
            # Hair covers top arc and sides
            draw.chord([x1, y1 - int(0.1 * height), x2, y2 + int(0.1 * height)], start=0, end=360, fill=255)
            draw.rectangle([x1, y1, x2, int(0.32 * height)], fill=255)
        elif reg_clean in ("mouth", "eyes", "eyebrows"):
            # Elliptical smooth region for eyes and mouth
            draw.ellipse([x1, y1, x2, y2], fill=255)
        elif reg_clean == "nose":
            # Triangular / trapezoidal nose contour
            points = [
                ((x1 + x2) // 2, y1),
                (x2, y2),
                (x1, y2),
            ]
            draw.polygon(points, fill=255)
            draw.ellipse([x1, y2 - int(0.08 * height), x2, y2], fill=255)
        elif reg_clean == "jaw":
            # Lower chin / jaw arc
            draw.chord([x1, y1, x2, y2], start=0, end=180, fill=255)
        else:
            # Default rounded rectangle for cheeks / forehead
            draw.rounded_rectangle([x1, y1, x2, y2], radius=16, fill=255)

        # Apply feathering for smooth inpainting boundaries
        if feather_radius > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))

        return mask

    def combine_masks(
        self,
        masks: List[Image.Image],
        image_size: Optional[Tuple[int, int]] = None,
    ) -> Image.Image:
        """Combines multiple region masks into a single union mask."""
        width, height = image_size or self.default_size
        combined = np.zeros((height, width), dtype=np.uint8)

        for m in masks:
            if m.size != (width, height):
                m = m.resize((width, height), Image.Resampling.BILINEAR)
            arr = np.array(m, dtype=np.uint8)
            combined = np.maximum(combined, arr)

        return Image.fromarray(combined, mode="L")


region_masker = FacialRegionMasker()
