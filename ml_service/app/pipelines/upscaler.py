"""
Upscaling, contrast sharpening, and responsible AI watermark pipeline.
Adheres to:
- MASTER_PROMPT.md §0 R11 Invariant 3 (Mandatory investigative aid disclaimer)
- MASTER_PROMPT.md §11 Step A6 (Upscale / finalize)
- contracts/schema.sql sha256 integrity hashing
"""

import hashlib
import io
import logging
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from ml_service.app.core.config import settings

logger = logging.getLogger("velora.ml.upscaler")


class PortraitFinalizer:
    """Handles high-fidelity portrait upscaling, line contrast enhancement, and watermark stamping."""

    def __init__(self):
        self.disclaimer_text = settings.DISCLAIMER_V1

    def upscale_image(
        self,
        image: Image.Image,
        scale_factor: int = 2,
        enhance_contrast: bool = True,
    ) -> Image.Image:
        """
        Upscales image by 2x or 4x using high-quality Lanczos resampling.
        Optionally enhances sketch line contrast for crisp printing.
        """
        if scale_factor not in (1, 2, 4):
            raise ValueError(f"Unsupported scale_factor {scale_factor}. Supported values: 1, 2, 4")

        orig_w, orig_h = image.size
        new_w = orig_w * scale_factor
        new_h = orig_h * scale_factor

        if scale_factor > 1:
            upscaled = image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
        else:
            upscaled = image.copy()

        if enhance_contrast:
            # Subtle pencil contrast enhancement
            enhancer = ImageEnhance.Contrast(upscaled)
            upscaled = enhancer.enhance(1.15)
            # Subtle sharpness boost
            sharpener = ImageEnhance.Sharpness(upscaled)
            upscaled = sharpener.enhance(1.20)

        return upscaled

    def apply_disclaimer_watermark(
        self,
        image: Image.Image,
        disclaimer_text: Optional[str] = None,
    ) -> Image.Image:
        """
        Stamps an unmistakable official disclaimer footer banner at the bottom of the portrait,
        satisfying R11 Invariant 3: 'AI-generated investigative aid — not a photograph, not evidence of identity.'
        """
        text = disclaimer_text or self.disclaimer_text
        img = image.convert("RGBA")
        width, height = img.size

        # Create overlay layer
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        banner_height = max(28, int(height * 0.055))
        banner_top = height - banner_height

        # Draw semi-transparent dark banner background
        draw.rectangle([0, banner_top, width, height], fill=(15, 23, 42, 210))

        # Text rendering
        font_size = max(11, int(banner_height * 0.42))
        try:
            # Default PIL font fallback if truetype not found
            font = ImageFont.load_default()
        except Exception:
            font = None

        # Draw centered disclaimer text
        text_color = (255, 255, 255, 240)
        draw.text(
            (width // 2, banner_top + (banner_height // 2)),
            text,
            fill=text_color,
            anchor="mm",
            font=font,
        )

        final_composite = Image.alpha_composite(img, overlay)
        return final_composite.convert("RGB")

    def compute_sha256(self, image: Image.Image) -> str:
        """Computes SHA256 hex digest of the raw encoded PNG bytes for chain of custody."""
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return hashlib.sha256(buf.getvalue()).hexdigest()


portrait_finalizer = PortraitFinalizer()
