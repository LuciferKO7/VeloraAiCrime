"""
Zero-shot CLIP attribute verifier for forensic facial composite validation.
Adheres to:
- contracts/face_attributes.schema.json enum definitions
- MASTER_PROMPT.md §11 Step A3 requirements
- Strict resource bounds: runs on CPU by default to preserve the 4 GB VRAM ceiling.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image
import torch

from ml_service.app.core.config import settings

logger = logging.getLogger("velora.ml.attribute_verifier")

# Official attribute enums extracted directly from contracts/face_attributes.schema.json
ATTRIBUTE_ENUM_REGISTRY: Dict[str, List[str]] = {
    "sex_presentation": ["male", "female", "unspecified"],
    "age_band": ["child", "teen", "young_adult", "adult", "middle_aged", "senior"],
    "appearance_group": [
        "south_asian",
        "east_asian",
        "southeast_asian",
        "white",
        "black",
        "middle_eastern",
        "latino",
        "mixed_other",
        "unspecified",
    ],
    "face_shape": ["oval", "round", "square", "long", "heart", "diamond", "rectangular"],
    "skin_tone": ["very_fair", "fair", "wheatish", "medium_brown", "brown", "dark_brown", "dark"],
    "forehead": ["low", "medium", "high"],
    "cheeks": ["hollow", "average", "full", "high_cheekbones"],
    "jaw_shape": ["pointed", "rounded", "square", "angular"],
    "jaw_width": ["narrow", "medium", "wide"],
    "chin": ["pointed", "rounded", "square", "cleft", "receding", "prominent"],
    "eye_shape": ["almond", "round", "hooded", "deep_set", "upturned", "downturned"],
    "eye_size": ["small", "medium", "large"],
    "eye_spacing": ["close", "average", "wide"],
    "eye_color": ["black", "dark_brown", "brown", "light_brown", "hazel", "green", "blue", "grey"],
    "eyebrow_thickness": ["thin", "medium", "thick", "bushy"],
    "eyebrow_shape": ["straight", "arched", "curved", "joined"],
    "nose_bridge": ["narrow", "medium", "broad"],
    "nose_length": ["short", "medium", "long"],
    "nose_tip": ["pointed", "rounded", "bulbous", "upturned"],
    "nostrils": ["narrow", "medium", "flared"],
    "lips_fullness": ["thin", "medium", "full"],
    "mouth_width": ["small", "medium", "wide"],
    "ears": ["small", "medium", "large", "protruding"],
    "hair_length": ["bald", "shaved", "short", "medium", "long"],
    "hair_style": ["straight", "wavy", "curly", "receding", "spiky", "bun", "ponytail"],
    "hair_color": ["black", "dark_brown", "brown", "grey", "white", "dyed_other"],
    "hairline": ["straight", "receding", "widows_peak", "high"],
    "facial_hair_type": ["none", "stubble", "mustache", "beard", "goatee", "sideburns", "mustache_and_beard"],
    "facial_hair_density": ["light", "medium", "dense"],
    "facial_hair_length": ["short", "medium", "long"],
    "glasses": ["none", "rimmed", "rimless", "sunglasses"],
    "headwear": ["none", "cap", "turban", "scarf", "hood", "helmet"],
}


def build_candidate_prompt(attribute_name: str, enum_val: str) -> str:
    """Construct natural language probe for CLIP zero-shot classification aligned with sketch textures."""
    clean_val = enum_val.replace("_", " ")

    if attribute_name == "hair_length":
        if enum_val == "bald":
            return "a forensic sketch portrait of a completely bald person with no hair"
        return f"a forensic sketch portrait of a person with {clean_val} hair"

    if attribute_name == "sex_presentation":
        if enum_val == "male":
            return "a forensic sketch portrait of a man"
        if enum_val == "female":
            return "a forensic sketch portrait of a woman"
        return "a forensic sketch portrait of a person"

    if attribute_name == "age_band":
        return f"a forensic sketch portrait of a {clean_val} person"

    if attribute_name == "facial_hair_type":
        if enum_val == "none":
            return "a forensic sketch portrait of a clean-shaven person without facial hair"
        return f"a forensic sketch portrait of a person with a {clean_val}"

    if attribute_name == "glasses":
        if enum_val == "none":
            return "a forensic sketch of a person with no glasses"
        return f"a forensic sketch of a person wearing {clean_val} glasses"

    if attribute_name == "hair_color":
        return f"a forensic sketch of a person with {clean_val} colored hair"

    if attribute_name == "eye_color":
        return f"a forensic sketch close-up portrait of a person with {clean_val} eyes"

    clean_attr = attribute_name.replace("_", " ")
    return f"a forensic sketch portrait of a person with {clean_val} {clean_attr}"


class CLIPAttributeVerifier:
    """Zero-shot CLIP verifier evaluating semantic attribute alignment and adherence."""

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32", device: Optional[str] = None):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() and not settings.LOW_VRAM_MODE else "cpu")
        self._model = None
        self._processor = None
        self._initialized = False

    def load_model(self) -> None:
        """Lazily loads CLIP model and processor."""
        if self._initialized:
            return

        logger.info("Loading CLIPAttributeVerifier model: %s on device=%s", self.model_name, self.device)
        from transformers import CLIPModel, CLIPProcessor

        self._processor = CLIPProcessor.from_pretrained(self.model_name)
        self._model = CLIPModel.from_pretrained(self.model_name).to(self.device)
        self._model.eval()
        self._initialized = True
        logger.info("CLIPAttributeVerifier loaded successfully.")

    def verify_attributes(
        self,
        image: Image.Image,
        requested_attributes: List[str],
        stated_attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates per-attribute probabilities across allowed enum values and computes attr_adherence.
        """
        self.load_model()
        stated_attributes = stated_attributes or {}
        attribute_scores: Dict[str, Dict[str, float]] = {}
        stated_probabilities: Dict[str, float] = {}

        # Evaluate each requested attribute
        for attr in requested_attributes:
            if attr not in ATTRIBUTE_ENUM_REGISTRY:
                continue

            candidate_enums = ATTRIBUTE_ENUM_REGISTRY[attr]
            prompts = [build_candidate_prompt(attr, val) for val in candidate_enums]

            inputs = self._processor(
                text=prompts,
                images=image,
                return_tensors="pt",
                padding=True,
            ).to(self.device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits_per_image = outputs.logits_per_image  # shape: [1, num_prompts]
                probs = torch.softmax(logits_per_image, dim=-1).squeeze(0).cpu().numpy()

            attr_score_map = {}
            for val, prob in zip(candidate_enums, probs):
                attr_score_map[val] = round(float(prob), 4)

            attribute_scores[attr] = attr_score_map

            # Check if this attribute was stated by the witness
            if attr in stated_attributes:
                stated_val = stated_attributes[attr]
                # Normalize stated_val if it was passed as dict or string
                if isinstance(stated_val, dict):
                    stated_val = stated_val.get("value")
                stated_val = str(stated_val) if stated_val is not None else None

                if stated_val and stated_val in attr_score_map:
                    stated_probabilities[attr] = attr_score_map[stated_val]

        # Calculate attr_adherence as the mean probability of stated attributes only
        attr_adherence: Optional[float] = None
        if len(stated_probabilities) > 0:
            attr_adherence = round(float(np.mean(list(stated_probabilities.values()))), 4)

        return {
            "attribute_scores": attribute_scores,
            "stated_probabilities": stated_probabilities,
            "attr_adherence": attr_adherence,
        }


# Global singleton instance (CPU-safe)
attribute_verifier = CLIPAttributeVerifier(device="cpu")
