"""Scene diagram model builder and validator conforming to contracts/scene.schema.json."""

from typing import Any

DEFAULT_EMPTY_SCENE = {
    "schema_version": "1.0",
    "canvas": {
        "unit": "normalized",
        "scale_confidence": "unknown",
        "approx_width_m": 25.0,
        "approx_height_m": 20.0
    },
    "environment": {
        "type": "outdoor",
        "description": "Commercial Street intersection, night setting",
        "lighting": "night"
    },
    "entities": [
        {
            "id": "ent-witness-1",
            "kind": "person",
            "label": "Witness W-001 Position",
            "x": 0.25,
            "y": 0.70,
            "heading_deg": 35.0,
            "confidence": "sure",
            "is_conflicted": False
        },
        {
            "id": "ent-suspect-1",
            "kind": "person",
            "label": "Suspect Location",
            "x": 0.55,
            "y": 0.40,
            "heading_deg": 190.0,
            "confidence": "sure",
            "is_conflicted": False
        },
        {
            "id": "ent-vehicle-1",
            "kind": "vehicle",
            "label": "Dark Sedan (Getaway)",
            "x": 0.78,
            "y": 0.35,
            "heading_deg": 90.0,
            "confidence": "somewhat",
            "is_conflicted": True
        },
        {
            "id": "ent-landmark-1",
            "kind": "landmark",
            "label": "ATM Kiosk Entrance",
            "x": 0.50,
            "y": 0.20,
            "heading_deg": 0.0,
            "confidence": "sure",
            "is_conflicted": False
        }
    ]
}

def validate_scene_data(data: dict[str, Any]) -> bool:
    """Basic structural validation against scene.schema.json requirements."""
    if data.get("schema_version") != "1.0":
        return False
    if "canvas" not in data or "environment" not in data or "entities" not in data:
        return False
    return True
