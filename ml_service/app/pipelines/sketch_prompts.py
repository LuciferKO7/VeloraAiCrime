"""
Forensic sketch prompt generation templates and rules for Velora ML Service.
Supports:
- Option A: Facial Composite Sketch (monochrome pencil drawing from facial attributes)
- Option B: Incident Storyboard Sketches (sequential narrative frame drawings)

Adheres to MASTER_PROMPT.md §9.3.4 base negative token preservation and R11 invariants.
"""

from typing import Any, Dict, List, Optional

# Mandatory 10 base negative tokens in exact sequence per §9.3.4
MANDATORY_BASE_NEGATIVE_TOKENS: List[str] = [
    "cartoon",
    "illustration",
    "deformed",
    "extra fingers",
    "watermark",
    "text",
    "blurry",
    "low quality",
    "multiple faces",
    "hat",
]

# Style-specific negative suppression terms for forensic monochrome sketches
SKETCH_NEGATIVE_SUPPRESSION_TOKENS: List[str] = [
    "photograph",
    "photorealistic",
    "3d render",
    "plastic skin",
    "glossy sheen",
    "color photograph",
    "vibrant colors",
    "heavy makeup",
    "oil painting",
    "airbrush",
    "bad anatomy",
    "disfigured",
    "frame",
    "border",
]

# Combined negative prompt
SKETCH_NEGATIVE_PROMPT: str = ", ".join(
    MANDATORY_BASE_NEGATIVE_TOKENS + SKETCH_NEGATIVE_SUPPRESSION_TOKENS
)


def extract_attribute_value(attr_obj: Any) -> Optional[str]:
    """Helper to safely extract string value from dictionary or string attribute."""
    if isinstance(attr_obj, dict):
        val = attr_obj.get("value")
        return str(val) if val is not None else None
    if isinstance(attr_obj, str) and attr_obj.strip():
        return attr_obj.strip()
    return None


def build_facial_composite_prompt(attributes: Dict[str, Any]) -> str:
    """
    Constructs a controlled forensic sketch positive prompt from structured witness attributes.
    Target token length: under 65 tokens.
    """
    parts = ["forensic pencil sketch, monochrome graphite drawing on paper"]

    # Age and gender presentation
    age = extract_attribute_value(attributes.get("age_band")) or extract_attribute_value(attributes.get("age"))
    sex = extract_attribute_value(attributes.get("sex_presentation")) or extract_attribute_value(attributes.get("gender"))

    subject_desc = "portrait of a person"
    if age and sex:
        subject_desc = f"portrait of an {age.replace('_', ' ')} {sex}"
    elif age:
        subject_desc = f"portrait of an {age.replace('_', ' ')} person"
    elif sex:
        subject_desc = f"portrait of a {sex}"
    parts.append(subject_desc)

    # Core clothing anchor (§4.1: plain crewneck covering shoulders)
    parts.append("wearing plain crewneck shirt covering shoulders")

    # Facial structure
    face_shape = extract_attribute_value(attributes.get("face_shape"))
    jawline = extract_attribute_value(attributes.get("jawline"))
    if face_shape or jawline:
        struct_desc = []
        if face_shape:
            struct_desc.append(f"{face_shape} face")
        if jawline:
            struct_desc.append(f"{jawline} jawline")
        parts.append(", ".join(struct_desc))

    # Eyes & Eyebrows
    eyes = extract_attribute_value(attributes.get("eyes"))
    eyebrows = extract_attribute_value(attributes.get("eyebrows"))
    if eyes or eyebrows:
        eye_desc = []
        if eyebrows:
            eye_desc.append(f"{eyebrows} eyebrows")
        if eyes:
            eye_desc.append(f"{eyes} eyes")
        parts.append(", ".join(eye_desc))

    # Nose & Mouth
    nose = extract_attribute_value(attributes.get("nose"))
    mouth = extract_attribute_value(attributes.get("mouth"))
    if nose:
        parts.append(f"{nose} nose")
    if mouth:
        parts.append(f"{mouth} lips")

    # Hair & Facial Hair
    hair = extract_attribute_value(attributes.get("hair"))
    facial_hair = extract_attribute_value(attributes.get("facial_hair"))
    if hair:
        parts.append(f"{hair} hair")
    if facial_hair and facial_hair != "none":
        parts.append(f"{facial_hair}")

    # Distinguishing marks
    marks = extract_attribute_value(attributes.get("distinguishing_features")) or extract_attribute_value(attributes.get("marks"))
    if marks:
        parts.append(f"visible {marks}")

    # Composition & framing style anchor
    parts.append("centered head-and-shoulders, clean neutral background, detailed line hatching, non-photorealistic")

    return ", ".join(parts)


def build_storyboard_frame_prompt(
    event_description: str,
    action: Optional[str] = None,
    characters: Optional[List[str]] = None,
    objects: Optional[List[str]] = None,
    location: Optional[str] = None,
    is_uncertain: bool = False,
) -> str:
    """
    Constructs a controlled forensic storyboard frame prompt for sequential action scenes.
    """
    parts = ["forensic incident storyboard sketch, monochrome graphite line art on paper"]

    # Frame scene action
    clean_desc = event_description.strip()
    if action and action.strip() and action.strip() not in clean_desc:
        parts.append(f"{action.strip()}, {clean_desc}")
    else:
        parts.append(clean_desc)

    # Location / Environment
    if location and location.strip():
        parts.append(f"setting: {location.strip()}")

    # Characters involved
    if characters:
        chars_str = ", ".join(c.strip() for c in characters if c.strip())
        if chars_str:
            parts.append(f"figures: {chars_str}")

    # Objects of interest
    if objects:
        objs_str = ", ".join(o.strip() for o in objects if o.strip())
        if objs_str:
            parts.append(f"objects: {objs_str}")

    # Uncertainty styling
    if is_uncertain:
        parts.append("soft illustrative pencil lines, speculative sketch rendering")
    else:
        parts.append("crisp pencil contours, clear spatial composition")

    parts.append("wide establishing angle, simple hatched shading, clean white background, non-photorealistic")

    return ", ".join(parts)
