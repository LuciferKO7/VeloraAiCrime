import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

SALIENT_KEYS = [
    "face_shape",
    "age_band",
    "hair_length",
    "hair_style",
    "facial_hair_type",
    "skin_tone",
    "eye_shape",
    "nose_bridge",
    "jaw_shape",
    "glasses",
    "headwear",
    "eyebrow_thickness",
    "lips_fullness",
    "ears",
    "forehead",
    "cheeks",
    "chin",
    "hair_color",
    "eye_color",
]


def assemble_session_state(conn: Connection, session_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Assembles the authoritative SessionState per §7.1 from persisted database rows:
    - statements
    - rounds with associated images
    - attributes from latest snapshot
    - assumptions derived per §8.5
    - locked features
    """
    sid = session_dict["id"]

    # 1. Attributes from current snapshot
    attributes: dict[str, Any] = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}
    snap_id = session_dict.get("current_snapshot_id")
    if snap_id:
        snap_row = conn.execute(
            text("SELECT attributes_json FROM attribute_snapshots WHERE id = :snap_id"),
            {"snap_id": snap_id},
        ).fetchone()
        if snap_row and snap_row[0]:
            try:
                attributes = json.loads(snap_row[0])
            except Exception:
                attributes = {"schema_version": "1.0", "attributes": {}, "unmapped_notes": []}

    # 2. Assumptions panel derivation (§8.5)
    assumptions: list[dict[str, Any]] = []
    attr_map = attributes.get("attributes") or {}
    for key in SALIENT_KEYS:
        item = attr_map.get(key)
        if not item or item.get("value") is None:
            assumptions.append({"key": key, "value": None, "reason": "not_stated_varied_across_variants"})
        elif item.get("source") == "inferred":
            assumptions.append({"key": key, "value": item.get("value"), "reason": "inferred_from_wording"})

    # 3. Locked features
    locked_features = []
    if session_dict.get("locked_features_json"):
        try:
            locked_features = json.loads(session_dict["locked_features_json"])
        except Exception:
            locked_features = []

    # 4. Statements
    stmt_rows = conn.execute(
        text(
            """
            SELECT id, session_id, speaker, original_text, original_lang, english_text,
                   translation_engine, input_mode, audio_sha256, created_by, created_at
            FROM statements
            WHERE session_id = :sid
            ORDER BY created_at ASC
            """
        ),
        {"sid": sid},
    ).mappings().fetchall()
    statements = [dict(r) for r in stmt_rows]

    # 5. Rounds with nested images
    round_rows = conn.execute(
        text(
            """
            SELECT id, session_id, round_no, kind, status, params_json, attribute_snapshot_id,
                   error, created_by, created_at, finished_at
            FROM rounds
            WHERE session_id = :sid
            ORDER BY round_no ASC
            """
        ),
        {"sid": sid},
    ).mappings().fetchall()

    rounds = []
    for r_row in round_rows:
        rid = r_row["id"]
        img_rows = conn.execute(
            text(
                """
                SELECT id, round_id, parent_image_id, variant_index, kind, width, height, seed,
                       variant_axes_json, sketch_sha256, storage_path, sketch_path,
                       model_versions_json, attr_adherence, identity_similarity, speculative,
                       is_final, created_at
                FROM images
                WHERE round_id = :rid
                ORDER BY variant_index ASC
                """
            ),
            {"rid": rid},
        ).mappings().fetchall()

        images = []
        for img in img_rows:
            img_id = img["id"]
            variant_axes = {}
            if img["variant_axes_json"]:
                try:
                    variant_axes = json.loads(img["variant_axes_json"])
                except Exception:
                    variant_axes = {}

            model_versions = {}
            if img["model_versions_json"]:
                try:
                    model_versions = json.loads(img["model_versions_json"])
                except Exception:
                    model_versions = {}

            images.append(
                {
                    "id": img_id,
                    "round_id": img["round_id"],
                    "parent_image_id": img["parent_image_id"],
                    "variant_index": img["variant_index"],
                    "kind": img["kind"],
                    "width": img["width"],
                    "height": img["height"],
                    "seed": img["seed"],
                    "variant_axes": variant_axes,
                    "attr_adherence": img["attr_adherence"],
                    "identity_similarity": img["identity_similarity"],
                    "speculative": bool(img["speculative"]),
                    "is_final": bool(img["is_final"]),
                    "has_sketch": bool(img["sketch_path"]),
                    "urls": {
                        "photo": f"/api/v1/images/{img_id}/file?style=photo",
                        "pencil": f"/api/v1/images/{img_id}/file?style=pencil",
                        "thumb": f"/api/v1/images/{img_id}/file?style=photo&size=thumb",
                    },
                    "model_versions": model_versions,
                    "created_at": img["created_at"],
                }
            )

        params = {}
        if r_row["params_json"]:
            try:
                params = json.loads(r_row["params_json"])
            except Exception:
                params = {}

        rounds.append(
            {
                "id": rid,
                "session_id": r_row["session_id"],
                "round_no": r_row["round_no"],
                "kind": r_row["kind"],
                "status": r_row["status"],
                "params": params,
                "images": images,
                "error": r_row["error"],
                "created_at": r_row["created_at"],
                "finished_at": r_row["finished_at"],
            }
        )

    return {
        "id": session_dict["id"],
        "case_id": session_dict["case_id"],
        "witness_id": session_dict["witness_id"],
        "kind": session_dict["kind"],
        "status": session_dict["status"],
        "current_round": session_dict["current_round"],
        "attributes": attributes,
        "assumptions": assumptions,
        "locked_features": locked_features,
        "selected_image_id": session_dict.get("selected_image_id"),
        "statements": statements,
        "rounds": rounds,
        "created_at": session_dict["created_at"],
        "updated_at": session_dict.get("updated_at") or session_dict["created_at"],
    }

