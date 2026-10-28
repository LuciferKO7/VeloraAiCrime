"""
Full End-to-End Workflow Execution Test (Runs 1 and 2).
Executes:
Witness input -> 6 sketch variants -> selection -> preference refinement -> mask edit -> required transformations -> finalization/export.
Uses live ML FastAPI endpoints with real model generation.
"""

import base64
import hashlib
import io
import json
import logging
import time
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from ml_service.app.core.config import settings
from ml_service.app.main import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("velora.e2e_workflow")

client = TestClient(app)
AUTH_HEADERS = {"X-Service-Key": settings.SERVICE_KEY}


def execute_workflow_run(run_id: int, subject_case: dict) -> dict:
    logger.info("=================================================================")
    logger.info("STARTING END-TO-END WORKFLOW RUN %d (Case: %s)", run_id, subject_case["case_id"])
    logger.info("=================================================================")
    t_start = time.perf_counter()
    metrics = {"run_id": run_id, "case_id": subject_case["case_id"], "steps": {}}

    # -------------------------------------------------------------------------
    # Step 1: Witness Input -> Generate Initial 6 Sketch Variants
    # -------------------------------------------------------------------------
    logger.info("[Run %d - Step 1] Generating 6 initial sketch variants...", run_id)
    payload_gen = {
        "module_type": "facial_composite",
        "case_id": subject_case["case_id"],
        "seed": subject_case["base_seed"],
        "num_variants": 6,
        "image_size": 512,
        "num_inference_steps": 3,
        "guidance_scale": 1.5,
        "facial_attributes": subject_case["attributes"],
    }
    res_gen = client.post("/ml/v1/generate", json=payload_gen, headers=AUTH_HEADERS)
    assert res_gen.status_code == 200, f"Generate failed: {res_gen.text}"
    data_gen = res_gen.json()
    assert data_gen["count"] == 6
    assert len(data_gen["images"]) == 6
    for it in data_gen["images"]:
        assert it["width"] == 512 and it["height"] == 512
        assert it["image_base64"].startswith("data:image/png;base64,")

    v1_b64 = data_gen["images"][1]["image_base64"]  # Pick variant index 1 (Variant 2)
    metrics["steps"]["generate_6_variants"] = {
        "status": "PASS",
        "count": len(data_gen["images"]),
        "latency_sec": round(data_gen.get("latency_sec", 0.0), 2),
        "peak_vram_mb": data_gen.get("peak_vram_mb", 0.0),
        "attr_adherence": [it.get("attr_adherence") for it in data_gen["images"]],
    }
    logger.info("[Run %d - Step 1 PASS] 6 variants generated in %.2fs", run_id, data_gen.get("latency_sec", 0.0))

    # -------------------------------------------------------------------------
    # Step 2: Witness Selection -> Preference Refinement & Evolution (Round 2)
    # -------------------------------------------------------------------------
    logger.info("[Run %d - Step 2] Submitting witness selection and evolving preference grid...", run_id)
    payload_evolve = {
        "session_id": f"session-e2e-run{run_id}",
        "case_id": subject_case["case_id"],
        "round_number": 2,
        "base_attributes": subject_case["attributes"],
        "feedback_events": [
            {
                "event_type": "select",
                "variant_axes": {
                    "jaw_prominence": 0.5,
                    "eye_openness": -0.4,
                    "cheek_fullness": 0.3,
                },
            }
        ],
        "current_preference_vector": None,
        "num_variants": 6,
        "seed": subject_case["base_seed"] + 100,
        "image_size": 512,
    }
    res_evolve = client.post("/ml/v1/evolve", json=payload_evolve, headers=AUTH_HEADERS)
    assert res_evolve.status_code == 200, f"Evolve failed: {res_evolve.text}"
    data_evolve = res_evolve.json()
    assert len(data_evolve["variants"]) == 6
    pref_vec = data_evolve["preference_vector"]
    assert pref_vec["jaw_prominence"] > 0.0  # Positively updated from select
    selected_evolved_b64 = data_evolve["variants"][0]["image_base64"]

    metrics["steps"]["preference_evolution"] = {
        "status": "PASS",
        "round_number": data_evolve["round_number"],
        "variants_count": len(data_evolve["variants"]),
        "updated_jaw_prominence": pref_vec["jaw_prominence"],
    }
    logger.info("[Run %d - Step 2 PASS] Preference vector updated; 6 evolved variants rendered.", run_id)

    # -------------------------------------------------------------------------
    # Step 3: Localized Anatomical Mask Edit
    # -------------------------------------------------------------------------
    logger.info("[Run %d - Step 3] Executing regional mask edit on selected portrait...", run_id)
    payload_edit = {
        "image_b64": selected_evolved_b64,
        "region": "eyebrows",
        "edit_instruction": "thicker natural arched eyebrows",
        "seed": subject_case["base_seed"] + 200,
        "strength": 0.75,
        "feather_radius": 8,
    }
    res_edit = client.post("/ml/v1/edit", json=payload_edit, headers=AUTH_HEADERS)
    assert res_edit.status_code == 200, f"Edit failed: {res_edit.text}"
    data_edit = res_edit.json()
    assert data_edit["status"] == "ok"
    assert "image_base64" in data_edit
    assert "mask_used_base64" in data_edit

    # Verify preservation of outside-region pixels
    src_bytes = base64.b64decode(selected_evolved_b64.split(",")[1])
    dst_bytes = base64.b64decode(data_edit["image_base64"].split(",")[1])
    im_src = Image.open(io.BytesIO(src_bytes))
    im_dst = Image.open(io.BytesIO(dst_bytes))
    assert im_src.size == im_dst.size == (512, 512)

    # Bottom area (e.g. row y=480) is completely outside eyebrows; pixels should be identical
    px_src = im_src.crop((100, 470, 400, 500)).tobytes()
    px_dst = im_dst.crop((100, 470, 400, 500)).tobytes()
    assert px_src == px_dst, "Outside-region pixels were not strictly preserved!"

    edited_b64 = data_edit["image_base64"]
    metrics["steps"]["mask_edit"] = {
        "status": "PASS",
        "region": data_edit["region"],
        "outside_pixels_preserved": True,
    }
    logger.info("[Run %d - Step 3 PASS] Eyebrow region edited with feathered blending; outside pixels 100%% preserved.", run_id)

    # -------------------------------------------------------------------------
    # Step 4: Forensic Transformations
    # -------------------------------------------------------------------------
    logger.info("[Run %d - Step 4] Executing required transformations (age, disguise, profile)...", run_id)
    transform_results = {}

    for kind in ["age_progression", "disguise_removal", "side_profile"]:
        payload_tf = {
            "image_b64": edited_b64,
            "transform_kind": kind,
            "target_disguise": "glasses" if kind == "disguise_removal" else None,
            "age_delta_years": 20,
            "seed": subject_case["base_seed"] + 300,
        }
        res_tf = client.post("/ml/v1/transform", json=payload_tf, headers=AUTH_HEADERS)
        assert res_tf.status_code == 200, f"Transform {kind} failed: {res_tf.text}"
        data_tf = res_tf.json()
        assert data_tf["status"] == "ok"
        assert data_tf["speculative"] is True, f"Transform {kind} missing speculative=True flag!"
        transform_results[kind] = {
            "status": "PASS",
            "schema_kind": data_tf["schema_kind"],
            "speculative": data_tf["speculative"],
        }

    metrics["steps"]["transformations"] = transform_results
    logger.info("[Run %d - Step 4 PASS] All 3 transformations executed with mandatory speculative=True flag.", run_id)

    # -------------------------------------------------------------------------
    # Step 5: Portrait Finalization and Export
    # -------------------------------------------------------------------------
    logger.info("[Run %d - Step 5] Executing finalization and export upscaling...", run_id)
    payload_fin = {
        "image_b64": edited_b64,
        "scale_factor": 2,
        "apply_watermark": True,
        "enhance_contrast": True,
    }
    res_fin = client.post("/ml/v1/finalize", json=payload_fin, headers=AUTH_HEADERS)
    assert res_fin.status_code == 200, f"Finalize failed: {res_fin.text}"
    data_fin = res_fin.json()
    assert data_fin["status"] == "ok"
    assert data_fin["original_width"] == 512 and data_fin["original_height"] == 512
    assert data_fin["final_width"] == 1024 and data_fin["final_height"] == 1024
    assert data_fin["scale_factor"] == 2
    assert settings.DISCLAIMER_V1 in data_fin["disclaimer"]

    # Verify SHA-256 integrity
    fin_raw = base64.b64decode(data_fin["image_base64"].split(",")[1])
    computed_sha = hashlib.sha256(fin_raw).hexdigest()
    assert computed_sha == data_fin["sha256"], f"Integrity check failed: {computed_sha} != {data_fin['sha256']}"

    metrics["steps"]["finalization"] = {
        "status": "PASS",
        "output_dimensions": f"{data_fin['final_width']}x{data_fin['final_height']}",
        "sha256": data_fin["sha256"],
        "disclaimer_verified": True,
    }

    dt_total = time.perf_counter() - t_start
    metrics["total_latency_sec"] = round(dt_total, 2)
    metrics["status"] = "PASS"
    logger.info("=================================================================")
    logger.info("END-TO-END WORKFLOW RUN %d COMPLETED SUCCESSFULLY IN %.2fs", run_id, dt_total)
    logger.info("=================================================================\n")
    return metrics


def run_full_workflow_twice():
    case_1 = {
        "case_id": "velora-e2e-witness-case-001",
        "base_seed": 8800,
        "attributes": {
            "sex_presentation": {"value": "man"},
            "age_band": {"value": "adult"},
            "face_shape": {"value": "square"},
            "hair": {"value": "short black"},
        },
    }

    case_2 = {
        "case_id": "velora-e2e-witness-case-002",
        "base_seed": 9200,
        "attributes": {
            "sex_presentation": {"value": "woman"},
            "age_band": {"value": "young_adult"},
            "face_shape": {"value": "oval"},
            "hair": {"value": "dark brown wavy"},
        },
    }

    report_run1 = execute_workflow_run(1, case_1)
    report_run2 = execute_workflow_run(2, case_2)

    all_passed = (report_run1["status"] == "PASS" and report_run2["status"] == "PASS")
    summary = {
        "workflow_passed_twice": all_passed,
        "run_1": report_run1,
        "run_2": report_run2,
    }

    repo_root = Path(__file__).resolve().parent.parent.parent
    report_path = repo_root / "ml_service" / "reports" / "full_workflow_e2e_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 70)
    print(f"FULL WORKFLOW E2E RELEASE GATE: {'PASS (COMPLETED TWICE)' if all_passed else 'FAIL'}")
    print("=" * 70)
    print(f"Run 1 Total Latency: {report_run1['total_latency_sec']}s")
    print(f"Run 2 Total Latency: {report_run2['total_latency_sec']}s")
    print(f"Output Report: {report_path}")
    print("=" * 70)
    return summary


if __name__ == "__main__":
    run_full_workflow_twice()
