#!/usr/bin/env python3
"""
Generate contracts/face_attributes.schema.json from Section 6.1 attribute table.
VELORA — MASTER PROMPT v1.1
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Complete attribute table from Section 6.1 (attribute_key: (region, [allowed_values]))
FACE_ATTRIBUTES_TABLE = {
    "sex_presentation": ("global", ["male", "female", "unspecified"]),
    "age_band": ("global", ["child", "teen", "young_adult", "adult", "middle_aged", "senior"]),
    "appearance_group": ("global", [
        "south_asian", "east_asian", "southeast_asian", "white",
        "black", "middle_eastern", "latino", "mixed_other", "unspecified"
    ]),
    "face_shape": ("global", ["oval", "round", "square", "long", "heart", "diamond", "rectangular"]),
    "skin_tone": ("skin", ["very_fair", "fair", "wheatish", "medium_brown", "brown", "dark_brown", "dark"]),
    "forehead": ("forehead", ["low", "medium", "high"]),
    "cheeks": ("cheeks", ["hollow", "average", "full", "high_cheekbones"]),
    "jaw_shape": ("jaw", ["pointed", "rounded", "square", "angular"]),
    "jaw_width": ("jaw", ["narrow", "medium", "wide"]),
    "chin": ("chin", ["pointed", "rounded", "square", "cleft", "receding", "prominent"]),
    "eye_shape": ("eyes", ["almond", "round", "hooded", "deep_set", "upturned", "downturned"]),
    "eye_size": ("eyes", ["small", "medium", "large"]),
    "eye_spacing": ("eyes", ["close", "average", "wide"]),
    "eye_color": ("eyes", ["black", "dark_brown", "brown", "light_brown", "hazel", "green", "blue", "grey"]),
    "eyebrow_thickness": ("eyebrows", ["thin", "medium", "thick", "bushy"]),
    "eyebrow_shape": ("eyebrows", ["straight", "arched", "curved", "joined"]),
    "nose_bridge": ("nose", ["narrow", "medium", "broad"]),
    "nose_length": ("nose", ["short", "medium", "long"]),
    "nose_tip": ("nose", ["pointed", "rounded", "bulbous", "upturned"]),
    "nostrils": ("nose", ["narrow", "medium", "flared"]),
    "lips_fullness": ("mouth", ["thin", "medium", "full"]),
    "mouth_width": ("mouth", ["small", "medium", "wide"]),
    "ears": ("ears", ["small", "medium", "large", "protruding"]),
    "hair_length": ("hair", ["bald", "shaved", "short", "medium", "long"]),
    "hair_style": ("hair", ["straight", "wavy", "curly", "receding", "spiky", "bun", "ponytail"]),
    "hair_color": ("hair", ["black", "dark_brown", "brown", "grey", "white", "dyed_other"]),
    "hairline": ("hair", ["straight", "receding", "widows_peak", "high"]),
    "facial_hair_type": ("facial_hair", [
        "none", "stubble", "mustache", "beard", "goatee", "sideburns", "mustache_and_beard"
    ]),
    "facial_hair_density": ("facial_hair", ["light", "medium", "dense"]),
    "facial_hair_length": ("facial_hair", ["short", "medium", "long"]),
    "glasses": ("glasses", ["none", "rimmed", "rimless", "sunglasses"]),
    "headwear": ("headwear", ["none", "cap", "turban", "scarf", "hood", "helmet"]),
}

MARK_TYPES = [
    "scar", "mole", "tattoo", "birthmark", "piercing", "wrinkle_lines", "acne_marks", "other"
]

MARK_LOCATIONS = [
    "left_cheek", "right_cheek", "forehead", "nose", "chin",
    "left_eyebrow", "right_eyebrow", "lip", "neck", "left_ear", "right_ear", "other"
]

CONFIDENCE_VALUES = ["sure", "somewhat", "unsure"]
SOURCE_VALUES = ["stated", "inferred", "default", "user_edit"]


def build_schema() -> dict:
    attribute_properties = {}
    for key, (region, allowed_values) in FACE_ATTRIBUTES_TABLE.items():
        attribute_properties[key] = {
            "type": ["object", "null"],
            "description": f"Region: {region}",
            "properties": {
                "value": {
                    "type": ["string", "null"],
                    "enum": allowed_values + [None]
                },
                "intensity": {
                    "type": ["number", "null"],
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "confidence": {
                    "type": ["string", "null"],
                    "enum": CONFIDENCE_VALUES + [None]
                },
                "source": {
                    "type": ["string", "null"],
                    "enum": SOURCE_VALUES + [None]
                }
            },
            "additionalProperties": False
        }

    marks_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": MARK_TYPES
                },
                "location": {
                    "type": "string",
                    "enum": MARK_LOCATIONS
                },
                "description": {"type": "string"},
                "confidence": {
                    "type": "string",
                    "enum": CONFIDENCE_VALUES
                },
                "source": {
                    "type": "string",
                    "enum": ["stated", "user_edit"]
                }
            },
            "required": ["type", "location", "description"],
            "additionalProperties": False
        }
    }

    attribute_properties["marks"] = marks_schema

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "FaceAttributes",
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": ["1.0"]
            },
            "attributes": {
                "type": "object",
                "properties": attribute_properties,
                "required": list(FACE_ATTRIBUTES_TABLE.keys()),
                "additionalProperties": False
            },
            "marks": marks_schema,
            "unmapped_notes": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["schema_version", "attributes"],
        "additionalProperties": False
    }
    return schema


def main():
    schema = build_schema()
    out_path = ROOT / "contracts" / "face_attributes.schema.json"
    out_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {out_path} with {len(FACE_ATTRIBUTES_TABLE)} attributes")


if __name__ == "__main__":
    main()
