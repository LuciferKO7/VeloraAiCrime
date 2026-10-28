import re
from typing import Any

# Allowed enum values per contracts/face_attributes.schema.json
ATTRIBUTE_ENUMS: dict[str, set[str]] = {
    "sex_presentation": {"male", "female", "unspecified"},
    "age_band": {"child", "teen", "young_adult", "adult", "middle_aged", "senior"},
    "appearance_group": {
        "south_asian",
        "east_asian",
        "southeast_asian",
        "white",
        "black",
        "middle_eastern",
        "latino",
        "mixed_other",
        "unspecified",
    },
    "face_shape": {"oval", "round", "square", "long", "heart", "diamond", "rectangular"},
    "skin_tone": {"very_fair", "fair", "wheatish", "medium_brown", "brown", "dark_brown", "dark"},
    "forehead": {"low", "medium", "high"},
    "cheeks": {"hollow", "average", "full", "high_cheekbones"},
    "jaw_shape": {"pointed", "rounded", "square", "angular"},
    "jaw_width": {"narrow", "medium", "wide"},
    "chin": {"pointed", "rounded", "square", "cleft", "receding", "prominent"},
    "eye_shape": {"almond", "round", "hooded", "deep_set", "upturned", "downturned"},
    "eye_size": {"small", "medium", "large"},
    "eye_spacing": {"close", "average", "wide"},
    "eye_color": {"black", "dark_brown", "brown", "light_brown", "hazel", "green", "blue", "grey"},
    "eyebrow_thickness": {"thin", "medium", "thick", "bushy"},
    "eyebrow_shape": {"straight", "arched", "curved", "joined"},
    "nose_bridge": {"narrow", "medium", "broad"},
    "nose_length": {"short", "medium", "long"},
    "nose_tip": {"pointed", "rounded", "bulbous", "upturned"},
    "nostrils": {"narrow", "medium", "flared"},
    "lips_fullness": {"thin", "medium", "full"},
    "mouth_width": {"small", "medium", "wide"},
    "ears": {"small", "medium", "large", "protruding"},
    "hair_length": {"bald", "shaved", "short", "medium", "long"},
    "hair_style": {"straight", "wavy", "curly", "receding", "spiky", "bun", "ponytail"},
    "hair_color": {"black", "dark_brown", "brown", "grey", "white", "dyed_other"},
    "hairline": {"straight", "receding", "widows_peak", "high"},
    "facial_hair_type": {"none", "stubble", "mustache", "beard", "goatee", "sideburns", "mustache_and_beard"},
    "facial_hair_density": {"light", "medium", "dense"},
    "facial_hair_length": {"short", "medium", "long"},
    "glasses": {"none", "rimmed", "rimless", "sunglasses"},
    "headwear": {"none", "cap", "turban", "scarf", "hood", "helmet"},
}

# Regex list in llm/guards.py covering explicit descriptors as words (§8.2)
APPEARANCE_GROUP_EXPLICIT_WORDS = re.compile(
    r"\b(south[\s_-]?asian|east[\s_-]?asian|southeast[\s_-]?asian|asian|indian|white|caucasian|black|african|middle[\s_-]?eastern|arab|latino|hispanic)\b",
    re.IGNORECASE,
)

SKIN_TONE_EXPLICIT_WORDS = re.compile(
    r"\b(very[\s_-]?fair|fair|wheatish|medium[\s_-]?brown|dark[\s_-]?brown|brown|dark|pale|tan|dusky|dark[\s_-]?skinned|fair[\s_-]?skinned)\b",
    re.IGNORECASE,
)

INFERRED_ALLOWED_KEYS = {"sex_presentation", "age_band"}


def validate_and_guard_parse_delta(
    delta: dict[str, Any],
    statement_english: str,
    extra_glossary_descriptors: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Applies post-validation guards (§8.2, TB3.8):
    1. Drop any key whose value is not in the schema enum.
    2. Force source='stated' for every key except sex_presentation / age_band.
       If source is 'inferred' on any other key, downgrade to dropped.
       Any source other than 'stated' or 'inferred' is dropped.
    3. Reject appearance_group and skin_tone unless the English statement contains
       an explicit descriptor word.
    4. Return (guarded_delta, dropped_items).
    """
    dropped_items: list[dict[str, Any]] = []
    attributes = delta.get("attributes", {})
    cleaned_attributes: dict[str, Any] = {}

    has_group_word = bool(APPEARANCE_GROUP_EXPLICIT_WORDS.search(statement_english))
    has_skin_word = bool(SKIN_TONE_EXPLICIT_WORDS.search(statement_english))

    if extra_glossary_descriptors:
        pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in extra_glossary_descriptors) + r")\b", re.IGNORECASE)
        if pattern.search(statement_english):
            has_group_word = True
            has_skin_word = True

    for key, attr_obj in attributes.items():
        if not isinstance(attr_obj, dict):
            dropped_items.append({"key": key, "reason": "Attribute value must be an object", "original": attr_obj})
            continue

        val = attr_obj.get("value")
        source = attr_obj.get("source")

        # Null value is allowed (or dropped from delta)
        if val is None:
            continue

        # 1. Whitelist validation
        allowed = ATTRIBUTE_ENUMS.get(key)
        if allowed is None:
            dropped_items.append({"key": key, "reason": f"Unknown attribute key '{key}'", "original": attr_obj})
            continue

        if val not in allowed:
            dropped_items.append({"key": key, "reason": f"Invalid enum value '{val}' for key '{key}'", "original": attr_obj})
            continue

        # 2. Source check
        if source not in ("stated", "inferred"):
            dropped_items.append({"key": key, "reason": f"Invalid source '{source}'", "original": attr_obj})
            continue

        if source == "inferred" and key not in INFERRED_ALLOWED_KEYS:
            dropped_items.append({
                "key": key,
                "reason": f"Inferred source not permitted on key '{key}' (allowed only on {sorted(INFERRED_ALLOWED_KEYS)})",
                "original": attr_obj,
            })
            continue

        # 3. Explicit descriptor check for appearance_group and skin_tone
        if key == "appearance_group" and not has_group_word:
            dropped_items.append({
                "key": key,
                "reason": "appearance_group rejected because statement does not contain an explicit appearance group descriptor",
                "original": attr_obj,
            })
            continue

        if key == "skin_tone" and not has_skin_word:
            dropped_items.append({
                "key": key,
                "reason": "skin_tone rejected because statement does not contain an explicit skin tone descriptor",
                "original": attr_obj,
            })
            continue

        # Passed all guards
        cleaned_attributes[key] = {
            "value": val,
            "intensity": attr_obj.get("intensity"),
            "confidence": attr_obj.get("confidence", "somewhat"),
            "source": source,
        }

    guarded_delta = {
        "attributes": cleaned_attributes,
        "marks": delta.get("marks", []),
        "unmapped_notes": delta.get("unmapped_notes", []),
        "ambiguities": delta.get("ambiguities", []),
    }

    return guarded_delta, dropped_items
