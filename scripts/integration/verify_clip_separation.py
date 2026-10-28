"""
CLIP Attribute Verifier Separation Experiment: Bald vs. Long Hair (Gate TA3.3).
Generates 12 matched bald portraits and 12 matched long-hair portraits using the
production generative pipeline and evaluates zero-shot CLIP probability separation.
"""

import json
import logging
import time
from pathlib import Path
import numpy as np
import torch

from ml_service.app.core.config import settings
from ml_service.app.models.manager import model_manager
from ml_service.app.pipelines.attribute_verifier import attribute_verifier
from ml_service.app.pipelines.sketch_prompts import (
    SKETCH_NEGATIVE_PROMPT,
    build_facial_composite_prompt,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("velora.verify_clip_separation")


def run_separation_experiment():
    repo_root = Path(__file__).resolve().parent.parent.parent
    reports_dir = repo_root / "ml_service" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_file = reports_dir / "ta3_3_clip_hair_separation.json"

    logger.info("Initializing pipeline for 12 bald and 12 long-hair matched portraits...")
    pipe = model_manager.load_pipeline(
        model_id=settings.DEFAULT_MODEL_ID,
        vae_id=settings.DEFAULT_VAE_ID,
        lcm_lora_id=settings.DEFAULT_LCM_LORA_ID,
    )

    use_cpu_generator = model_manager.low_vram_mode or "cuda" not in model_manager.device

    # Base matched attributes
    base_attrs = {
        "sex_presentation": {"value": "man"},
        "age_band": {"value": "adult"},
        "face_shape": {"value": "oval"},
    }

    bald_attrs = dict(base_attrs)
    bald_attrs["hair_length"] = {"value": "bald"}
    bald_prompt = build_facial_composite_prompt(bald_attrs)

    long_attrs = dict(base_attrs)
    long_attrs["hair_length"] = {"value": "long"}
    long_attrs["sex_presentation"] = {"value": "woman"}  # natural matched contrast
    long_prompt = build_facial_composite_prompt(long_attrs)

    bald_results = []
    long_results = []

    # 1. Generate and evaluate 12 Bald portraits
    logger.info("Generating 12 Bald portraits...")
    for idx in range(12):
        seed = 5000 + idx
        gen = torch.Generator(device="cpu" if use_cpu_generator else "cuda").manual_seed(seed)
        res = pipe(
            prompt=bald_prompt,
            negative_prompt=SKETCH_NEGATIVE_PROMPT,
            width=512,
            height=512,
            num_inference_steps=3,
            guidance_scale=1.5,
            generator=gen,
        )
        img = res.images[0]
        v_res = attribute_verifier.verify_attributes(
            image=img,
            requested_attributes=["hair_length"],
            stated_attributes=bald_attrs,
        )
        scores = v_res["attribute_scores"]["hair_length"]
        bald_prob = scores.get("bald", 0.0)
        long_prob = scores.get("long", 0.0)
        bald_results.append({
            "index": idx,
            "seed": seed,
            "bald_prob": bald_prob,
            "long_prob": long_prob,
            "all_scores": scores,
        })
        logger.info("Bald [%d/12] seed=%d -> bald_prob=%.4f, long_prob=%.4f", idx + 1, seed, bald_prob, long_prob)

    # 2. Generate and evaluate 12 Long Hair portraits
    logger.info("Generating 12 Long Hair portraits...")
    for idx in range(12):
        seed = 6000 + idx
        gen = torch.Generator(device="cpu" if use_cpu_generator else "cuda").manual_seed(seed)
        res = pipe(
            prompt=long_prompt,
            negative_prompt=SKETCH_NEGATIVE_PROMPT,
            width=512,
            height=512,
            num_inference_steps=3,
            guidance_scale=1.5,
            generator=gen,
        )
        img = res.images[0]
        v_res = attribute_verifier.verify_attributes(
            image=img,
            requested_attributes=["hair_length"],
            stated_attributes=long_attrs,
        )
        scores = v_res["attribute_scores"]["hair_length"]
        bald_prob = scores.get("bald", 0.0)
        long_prob = scores.get("long", 0.0)
        long_results.append({
            "index": idx,
            "seed": seed,
            "bald_prob": bald_prob,
            "long_prob": long_prob,
            "all_scores": scores,
        })
        logger.info("Long Hair [%d/12] seed=%d -> bald_prob=%.4f, long_prob=%.4f", idx + 1, seed, bald_prob, long_prob)

    # 3. Calculate statistics
    bald_group_bald_probs = [r["bald_prob"] for r in bald_results]
    bald_group_long_probs = [r["long_prob"] for r in bald_results]
    long_group_bald_probs = [r["bald_prob"] for r in long_results]
    long_group_long_probs = [r["long_prob"] for r in long_results]

    mean_bald_on_bald = float(np.mean(bald_group_bald_probs))
    mean_bald_on_long = float(np.mean(long_group_bald_probs))
    mean_long_on_bald = float(np.mean(bald_group_long_probs))
    mean_long_on_long = float(np.mean(long_group_long_probs))

    bald_separation_diff = mean_bald_on_bald - mean_bald_on_long
    long_separation_diff = mean_long_on_long - mean_long_on_bald

    experiment_report = {
        "sample_count_per_group": 12,
        "total_images": 24,
        "bald_group": {
            "mean_bald_prob": round(mean_bald_on_bald, 4),
            "std_bald_prob": round(float(np.std(bald_group_bald_probs)), 4),
            "mean_long_prob": round(mean_long_on_bald, 4),
            "individual_runs": bald_results,
        },
        "long_hair_group": {
            "mean_bald_prob": round(mean_bald_on_long, 4),
            "std_bald_prob": round(float(np.std(long_group_bald_probs)), 4),
            "mean_long_prob": round(mean_long_on_long, 4),
            "individual_runs": long_results,
        },
        "separation_metrics": {
            "mean_bald_on_bald": round(mean_bald_on_bald, 4),
            "mean_bald_on_long": round(mean_bald_on_long, 4),
            "bald_prob_difference": round(bald_separation_diff, 4),
            "long_prob_difference": round(long_separation_diff, 4),
            "separation_confirmed": bool(bald_separation_diff > 0.15 and long_separation_diff > 0.15),
        },
        "status": "PASS" if bald_separation_diff > 0.15 else "MARGINAL",
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(experiment_report, f, indent=2)

    print("\n" + "=" * 60)
    print("GATE TA3.3 CLIP HAIR SEPARATION RESULTS (12 vs 12)")
    print("=" * 60)
    print(f"Mean Bald Prob on Bald Group:      {mean_bald_on_bald:.4f}")
    print(f"Mean Bald Prob on Long Hair Group: {mean_bald_on_long:.4f}")
    print(f"Bald Separation Difference:        {bald_separation_diff:+.4f}")
    print(f"Mean Long Prob on Long Hair Group: {mean_long_on_long:.4f}")
    print(f"Mean Long Prob on Bald Group:      {mean_long_on_bald:.4f}")
    print(f"Long Hair Separation Difference:   {long_separation_diff:+.4f}")
    print(f"Separation Confirmed:              {experiment_report['separation_metrics']['separation_confirmed']}")
    print(f"Gate TA3.3 Status:                 {experiment_report['status']}")
    print("=" * 60)

    return experiment_report


if __name__ == "__main__":
    run_separation_experiment()
