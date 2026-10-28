"""A0 Generation Benchmark Script for Velora Person A.

Evaluates SD1.5 base checkpoint candidates with LCM-LoRA speed-up:
- Candidate 1: stable-diffusion-v1-5/stable-diffusion-v1-5 (or runwayml/stable-diffusion-v1-5)
- Candidate 2: SG161222/Realistic_Vision_V5.1_noVAE (+ stabilityai/sd-vae-ft-mse)
- LCM-LoRA: latent-consistency/lcm-lora-sdv1-5

Measures:
- Per-image latency & median seconds per image (target <= 3.0s @ 512px, 4 steps)
- Peak allocated GPU VRAM via torch.cuda.max_memory_allocated()
- Generates 24 images (6 prompts x 4 seeds) per candidate
- Produces contact sheet PNG in ml_service/reports/
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

BASE_NEGATIVE_PROMPT_TOKENS = [
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

BASELINE_NEGATIVE_PROMPT = ", ".join(BASE_NEGATIVE_PROMPT_TOKENS)
NEGATIVE_PROMPT = BASELINE_NEGATIVE_PROMPT

BASELINE_PROMPT_TEMPLATES = [
    "front portrait photo of a 35 year old man, short black hair, studio lighting, neutral background",
    "front portrait photo of a 28 year old woman, long wavy hair, oval face, neutral lighting",
    "front portrait photo of a 45 year old man, round face, thick mustache, short dark hair",
    "front portrait photo of a 30 year old woman, square jawline, fair skin, straight black hair",
    "front portrait photo of a 50 year old man, receding hairline, thin eyebrows, brown eyes",
    "front portrait photo of a 22 year old person, wheatish skin tone, pointed chin, dark brown eyes",
]
PROMPT_TEMPLATES = BASELINE_PROMPT_TEMPLATES

SEEDS = [42, 101, 2024, 777]

# Prompt-tuning experiment templates (preserving core attributes, removing generic studio triggers)
PROMPT_TUNING_TEMPLATES = [
    "realistic eyewitness portrait of a 35 year old man, short black hair, natural skin texture, visible pores, clear detailed eyes, soft natural light, neutral backdrop",
    "realistic eyewitness portrait of a 28 year old woman, long wavy hair, oval face, natural skin tone, subtle skin details, focused eyes, ambient daylight",
    "authentic portrait photograph of a 45 year old man, round face, thick mustache, short dark hair, natural facial features, realistic skin texture, neutral lighting",
    "realistic photo of a 30 year old woman, square jawline, fair skin, straight black hair, authentic skin texture, sharp detailed eyes, subtle natural shadows",
    "candid documentary portrait of a 50 year old man, receding hairline, thin eyebrows, brown eyes, realistic aged skin texture, natural expression, soft indoor lighting",
    "eyewitness composite portrait of a 22 year old person, wheatish skin tone, pointed chin, dark brown eyes, realistic skin pores, natural eye clarity, neutral studio background",
]

DEFECT_SUPPRESSION_TOKENS = [
    "plastic skin",
    "airbrushed",
    "3D render",
    "smooth porcelain skin",
    "fake eyes",
    "doll eyes",
    "cross-eyed",
    "deformed iris",
    "over-smoothed",
    "oversaturated",
    "beauty filter",
]

# Visual-tuning experiment V2 templates (standardized police composite framing, authentic skin, uniform lighting)
VISUAL_TUNING_V2_TEMPLATES = [
    "photographic witness portrait of a 35 year old man, short black hair, natural light stubble, angular jawline, balanced skin texture, frontal eye-level view, even diffuse soft lighting, solid neutral grey backdrop, wearing plain dark crewneck shirt",
    "photographic witness portrait of a 28 year old woman, long wavy dark brown hair, oval face, natural eye clarity, balanced skin texture, frontal eye-level view, even diffuse soft lighting, solid neutral grey backdrop, wearing plain neutral crewneck shirt",
    "photographic witness portrait of a 45 year old man, round face shape, thick natural mustache, short dark parted hair, authentic mature skin texture, frontal eye-level view, even diffuse soft lighting, solid neutral grey backdrop, wearing plain crewneck shirt",
    "photographic witness portrait of a 30 year old woman, square jawline, fair skin tone, straight black shoulder-length hair, authentic skin tone, frontal eye-level view, even diffuse soft lighting, solid neutral grey backdrop, wearing plain crewneck shirt",
    "photographic witness portrait of a 50 year old man, receding hairline, thin salt-and-pepper eyebrows, natural hooded brown eyes, authentic age lines, frontal eye-level view, even diffuse soft lighting, solid neutral grey backdrop, wearing plain crewneck shirt",
    "photographic witness portrait of a 22 year old young adult, wheatish skin tone, pointed chin, dark brown eyes, natural youthful skin texture, frontal eye-level view, even diffuse soft lighting, solid neutral grey backdrop, wearing plain crewneck shirt",
]

V2_CONSISTENCY_NEGATIVE_TOKENS = [
    "outdoor",
    "trees",
    "foliage",
    "nature",
    "bedroom",
    "lamp",
    "interior furniture",
    "shirtless",
    "bare shoulders",
    "naked",
    "cleavage",
    "low-cut",
    "harsh flash",
    "rim lighting",
    "lens flare",
    "film grain",
    "exaggerated pores",
    "oily skin",
    "greasy sheen",
    "high contrast skin",
]

# Preserve all base negative tokens while adding defect-suppression and V2 consistency tokens
VISUAL_TUNING_V2_NEGATIVE_PROMPT = ", ".join(
    BASE_NEGATIVE_PROMPT_TOKENS + DEFECT_SUPPRESSION_TOKENS + V2_CONSISTENCY_NEGATIVE_TOKENS
)

# Visual-tuning experiment V3 templates (unretouched documentary realism, balanced skin matte, centered eye-level gaze)
VISUAL_TUNING_V3_TEMPLATES = [
    # Scenario 1: 35yo man, short black hair
    "unretouched documentary portrait photograph of a 35 year old man, short black hair, natural light stubble, angular jawline, authentic matte skin texture with subtle imperfections, centered head-and-shoulders framing, frontal eye-level gaze, even diffuse soft lighting, plain solid neutral-grey studio background, wearing plain opaque dark crewneck shirt covering shoulders",
    # Scenario 2: 28yo woman, wavy hair, oval face
    "unretouched documentary portrait photograph of a 28 year old woman, long wavy dark brown hair, oval face shape, natural clear brown eyes, authentic unretouched skin texture with natural skin tone, centered head-and-shoulders framing, frontal eye-level gaze, even diffuse soft lighting, plain solid neutral-grey studio background, wearing plain opaque grey crewneck shirt covering shoulders",
    # Scenario 3: 45yo man, round face, thick mustache
    "unretouched documentary portrait photograph of a 45 year old man, round face shape, thick natural mustache, short dark combed hair, authentic mature skin texture with subtle age lines, centered head-and-shoulders framing, frontal eye-level gaze, even diffuse soft lighting, plain solid neutral-grey studio background, wearing plain opaque crewneck shirt covering shoulders",
    # Scenario 4: 30yo woman, square jawline, fair skin
    "unretouched documentary portrait photograph of a 30 year old woman, square jawline, fair skin tone, straight black shoulder-length hair, natural brown eyes, authentic unretouched skin with subtle natural variations, centered head-and-shoulders framing, frontal eye-level gaze, even diffuse soft lighting, plain solid neutral-grey studio background, wearing plain opaque crewneck shirt covering shoulders",
    # Scenario 5: 50yo man, receding hairline, thin eyebrows, brown eyes
    "unretouched documentary portrait photograph of a 50 year old man, receding hairline, thin salt-and-pepper eyebrows, natural hooded brown eyes, authentic mature skin with natural forehead lines, centered head-and-shoulders framing, frontal eye-level gaze, even diffuse soft lighting, plain solid neutral-grey studio background, wearing plain opaque crewneck shirt covering shoulders",
    # Scenario 6: 22yo person, wheatish skin, pointed chin, dark brown eyes
    "unretouched documentary portrait photograph of a 22 year old young adult, wheatish skin tone, pointed chin, dark brown eyes, authentic smooth youthful skin with natural matte finish, centered head-and-shoulders framing, frontal eye-level gaze, even diffuse soft lighting, plain solid neutral-grey studio background, wearing plain opaque crewneck shirt covering shoulders",
]

V3_ADDITIONAL_NEGATIVE_TOKENS = [
    "glossy skin",
    "cinematic lighting",
    "dramatic shadows",
    "fashion editorial",
    "beauty portrait",
    "heavy makeup",
    "lipstick",
    "eyeshadow",
    "eyeliner",
    "over-sharpened",
    "asymmetrical ears",
    "distorted teeth",
    "malformed ears",
    "collage",
    "split screen",
    "multiple views",
]

# Preserve all base negative tokens while adding defect-suppression, V2, and V3 targeted terms
VISUAL_TUNING_V3_NEGATIVE_PROMPT = ", ".join(
    BASE_NEGATIVE_PROMPT_TOKENS
    + DEFECT_SUPPRESSION_TOKENS
    + V2_CONSISTENCY_NEGATIVE_TOKENS
    + V3_ADDITIONAL_NEGATIVE_TOKENS
)

# Visual-tuning experiment V3.1 templates (curated concise prompts, clothing at front, strictly <= 65 tokens)
VISUAL_TUNING_V3_1_TEMPLATES = [
    # Scenario 1: 35yo man, short black hair
    "centered head-and-shoulders portrait of a 35 year old man wearing plain opaque crewneck shirt covering shoulders, short black hair, natural light stubble, angular jawline, realistic matte skin, natural eyes, diffuse soft lighting, solid neutral grey background",
    # Scenario 2: 28yo woman, wavy hair, oval face
    "centered head-and-shoulders portrait of a 28 year old woman wearing plain opaque crewneck shirt covering shoulders, long wavy dark hair, oval face, realistic skin texture, clear brown eyes, diffuse soft lighting, solid neutral grey background",
    # Scenario 3: 45yo man, round face, thick mustache
    "centered head-and-shoulders portrait of a 45 year old man wearing plain opaque crewneck shirt covering shoulders, round face, thick natural mustache, short dark hair, authentic mature skin, diffuse soft lighting, solid neutral grey background",
    # Scenario 4: 30yo woman, square jawline, fair skin
    "centered head-and-shoulders portrait of a 30 year old woman wearing plain opaque crewneck shirt covering shoulders, square jawline, fair skin, straight black hair, natural brown eyes, realistic skin, diffuse soft lighting, solid neutral grey background",
    # Scenario 5: 50yo man, receding hairline, thin eyebrows, brown eyes
    "centered head-and-shoulders portrait of a 50 year old man wearing plain opaque crewneck shirt covering shoulders, receding hairline, thin eyebrows, hooded brown eyes, natural mature skin lines, diffuse soft lighting, solid neutral grey background",
    # Scenario 6: 22yo person, wheatish skin, pointed chin, dark brown eyes
    "centered head-and-shoulders portrait of a 22 year old young adult wearing plain opaque crewneck shirt covering shoulders, wheatish skin tone, pointed chin, dark brown eyes, natural youthful skin, diffuse soft lighting, solid neutral grey background",
]

V3_1_DEFECT_TERMS = [
    "plastic skin",
    "airbrushed",
    "3D render",
    "doll eyes",
    "cross-eyed",
    "oversaturated",
    "beauty filter",
    "outdoor",
    "shirtless",
    "bare shoulders",
    "naked",
    "harsh lighting",
    "oily skin",
    "film grain",
]

# Preserve all base negative tokens while adding curated V3.1 terms (strictly <= 75 tokens)
VISUAL_TUNING_V3_1_NEGATIVE_PROMPT = ", ".join(BASE_NEGATIVE_PROMPT_TOKENS + V3_1_DEFECT_TERMS)


def create_contact_sheet(images: list[Image.Image], cols: int = 4, thumb_size: int = 256) -> Image.Image:
    """Create a contact sheet grid image from a list of PIL Images."""
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_size, rows * thumb_size), color=(240, 240, 240))

    for idx, img in enumerate(images):
        c = idx % cols
        r = idx // cols
        thumb = img.resize((thumb_size, thumb_size), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (c * thumb_size, r * thumb_size))
    return sheet



def run_candidate_benchmark(
    candidate_id: str,
    vae_id: str | None = None,
    lcm_lora_id: str = "latent-consistency/lcm-lora-sdv1-5",
    image_size: int = 512,
    num_inference_steps: int = 4,
    guidance_scale: float = 1.5,
    low_vram_mode: bool = False,
    prompt_templates: list[str] | None = None,
    negative_prompt: str | None = None,
    output_dir: Path | None = None,
) -> dict:
    from diffusers import AutoencoderKL, LCMScheduler, StableDiffusionPipeline

    prompts = prompt_templates if prompt_templates is not None else BASELINE_PROMPT_TEMPLATES
    neg_prompt = negative_prompt if negative_prompt is not None else BASELINE_NEGATIVE_PROMPT

    print(f"\n========================================================")
    print(f"BENCHMARKING CANDIDATE: {candidate_id}")
    print(f"VAE: {vae_id or 'default'} | LCM-LoRA: {lcm_lora_id}")
    print(f"Resolution: {image_size}x{image_size} | Steps: {num_inference_steps} | Low VRAM: {low_vram_mode}")
    print(f"Prompts count: {len(prompts)} | Seeds count: {len(SEEDS)}")
    print(f"========================================================")

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    vae = None
    if vae_id:
        print(f"Loading custom VAE: {vae_id}...")
        vae = AutoencoderKL.from_pretrained(vae_id, torch_dtype=torch.float16)

    print(f"Loading base pipeline: {candidate_id}...")
    pipe_kwargs = {
        "torch_dtype": torch.float16,
        "safety_checker": None,
    }
    if vae:
        pipe_kwargs["vae"] = vae

    pipe = StableDiffusionPipeline.from_pretrained(candidate_id, **pipe_kwargs)
    pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)

    print(f"Loading LCM-LoRA weights: {lcm_lora_id}...")
    pipe.load_lora_weights(lcm_lora_id)
    pipe.fuse_lora()

    if low_vram_mode:
        print("Enabling sequential CPU offload for 4GB VRAM safety...")
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.to("cuda")
        pipe.enable_attention_slicing()

    # Warm-up run
    print("Performing warm-up run (1 image)...")
    _ = pipe(
        prompt=prompts[0],
        negative_prompt=neg_prompt,
        width=image_size,
        height=image_size,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        generator=torch.Generator(device="cpu" if low_vram_mode else "cuda").manual_seed(0),
    ).images[0]
    torch.cuda.synchronize()

    torch.cuda.reset_peak_memory_stats()
    timings = []
    generated_images = []

    print(f"Running benchmark across {len(prompts)} prompts x {len(SEEDS)} seeds = {len(prompts) * len(SEEDS)} images...")
    img_counter = 0
    for p_idx, prompt in enumerate(prompts, 1):
        for s_idx, seed in enumerate(SEEDS, 1):
            img_counter += 1
            generator = torch.Generator(device="cpu" if low_vram_mode else "cuda").manual_seed(seed)
            torch.cuda.synchronize()
            t0 = time.perf_counter()

            result = pipe(
                prompt=prompt,
                negative_prompt=neg_prompt,
                width=image_size,
                height=image_size,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                generator=generator,
            )
            torch.cuda.synchronize()
            dt = time.perf_counter() - t0
            timings.append(dt)
            generated_images.append(result.images[0])
            print(f"  [{img_counter:02d}/24] Prompt {p_idx}, Seed {seed} -> {dt:.3f} s")

    median_sec = float(np.median(timings))
    mean_sec = float(np.mean(timings))
    p90_sec = float(np.percentile(timings, 90))
    peak_vram_bytes = torch.cuda.max_memory_allocated()
    peak_vram_mb = peak_vram_bytes / (1024**2)

    total_vram_bytes = torch.cuda.get_device_properties(0).total_memory
    total_vram_mb = total_vram_bytes / (1024**2)
    budget_limit_mb = (total_vram_bytes - (0.8 * 1024**3)) / (1024**2)

    vram_passed = peak_vram_mb < budget_limit_mb
    speed_passed = median_sec <= 3.0

    print(f"\nResults for {candidate_id}:")
    print(f"  Median Latency: {median_sec:.3f} s/image (Target: <= 3.0 s) -> {'PASS' if speed_passed else 'FAIL'}")
    print(f"  Mean Latency:   {mean_sec:.3f} s/image")
    print(f"  P90 Latency:    {p90_sec:.3f} s/image")
    print(f"  Peak VRAM:      {peak_vram_mb:.1f} MiB (Budget Limit: < {budget_limit_mb:.1f} MiB) -> {'PASS' if vram_passed else 'FAIL'}")
    print(f"  Total VRAM:     {total_vram_mb:.1f} MiB")

    # Save contact sheet
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = candidate_id.replace("/", "_")
        sheet = create_contact_sheet(generated_images, cols=4, thumb_size=256)
        sheet_path = output_dir / f"contact_sheet_{safe_name}.png"
        sheet.save(sheet_path)
        print(f"  Contact Sheet:  {sheet_path}")
        if "visual_tuning_v3_1" in str(output_dir):
            v3_1_sheet = output_dir / "contact_sheet_realistic_vision_v3_1.png"
            sheet.save(v3_1_sheet)
            print(f"  V3.1 Contact Sheet:  {v3_1_sheet}")
        elif "visual_tuning_v3" in str(output_dir):
            v3_sheet = output_dir / "contact_sheet_realistic_vision_v3.png"
            sheet.save(v3_sheet)
            print(f"  V3 Contact Sheet:  {v3_sheet}")

    # Unload pipeline
    del pipe
    if vae:
        del vae
    torch.cuda.empty_cache()

    from transformers import CLIPTokenizer
    tok = CLIPTokenizer.from_pretrained(candidate_id, subfolder="tokenizer")
    pos_token_counts = [len(tok(p)["input_ids"]) for p in prompts]
    neg_token_count = len(tok(neg_prompt)["input_ids"])

    return {
        "candidate": candidate_id,
        "vae": vae_id,
        "lcm_lora": lcm_lora_id,
        "image_size": image_size,
        "steps": num_inference_steps,
        "prompt_templates": prompts,
        "negative_prompt": neg_prompt,
        "positive_token_counts": pos_token_counts,
        "negative_token_count": neg_token_count,
        "timings_sec": timings,
        "median_sec": median_sec,
        "mean_sec": mean_sec,
        "p90_sec": p90_sec,
        "peak_vram_mb": peak_vram_mb,
        "total_vram_mb": total_vram_mb,
        "budget_limit_mb": budget_limit_mb,
        "speed_passed": speed_passed,
        "vram_passed": vram_passed,
    }



def main():
    parser = argparse.ArgumentParser(description="A0 Generation Benchmark")
    parser.add_argument("--image-size", type=int, default=512, help="Output image size (512 or 448)")
    parser.add_argument("--steps", type=int, default=4, help="LCM inference steps (default: 4)")
    default_low_vram = os.environ.get("LOW_VRAM_MODE", "true").lower() in ("true", "1")
    parser.add_argument("--low-vram", action="store_true", default=default_low_vram, help="Force sequential CPU offload")
    parser.add_argument(
        "--prompt-set",
        choices=["baseline", "prompt_tuning", "visual_tuning_v2", "visual_tuning_v3", "visual_tuning_v3_1"],
        default="baseline",
        help="Prompt set to evaluate ('baseline', 'prompt_tuning', 'visual_tuning_v2', 'visual_tuning_v3', or 'visual_tuning_v3_1')",
    )
    parser.add_argument(
        "--candidate",
        choices=["all", "sd15", "realistic_vision"],
        default="all",
        help="Which candidate to run ('all', 'sd15', or 'realistic_vision')",
    )
    parser.add_argument("--output-dir", type=str, default="ml_service/reports", help="Reports directory")
    args = parser.parse_args()

    reports_dir = Path(args.output_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.candidate == "all":
        import subprocess

        # Run each candidate in an isolated process to prevent CPU offload hook contamination in torch_cpu.dll
        cmd_base = [
            sys.executable,
            __file__,
            "--image-size", str(args.image_size),
            "--steps", str(args.steps),
            "--prompt-set", args.prompt_set,
            "--output-dir", str(args.output_dir),
        ]
        if args.low_vram:
            cmd_base.append("--low-vram")

        all_results = []
        for cand_name in ["sd15", "realistic_vision"]:
            print(f"\n>>> Spawning isolated subprocess for candidate: {cand_name} <<<")
            sub_cmd = cmd_base + ["--candidate", cand_name]
            p = subprocess.run(sub_cmd, check=True)

        # Merge individual candidate reports
        report_sd15 = reports_dir / "benchmark_report_sd15.json"
        report_rv = reports_dir / "benchmark_report_realistic_vision.json"
        merged = []
        for rpath in [report_sd15, report_rv]:
            if rpath.exists():
                with open(rpath, "r") as f:
                    merged.append(json.load(f))
                rpath.unlink(missing_ok=True)

        summary_file = reports_dir / "benchmark_report.json"
        with open(summary_file, "w") as f:
            json.dump(merged, f, indent=2)
        print(f"\nAll benchmark results merged and saved to: {summary_file}")
        return

    if args.prompt_set == "visual_tuning_v3_1":
        selected_prompts = VISUAL_TUNING_V3_1_TEMPLATES
        selected_neg = VISUAL_TUNING_V3_1_NEGATIVE_PROMPT
    elif args.prompt_set == "visual_tuning_v3":
        selected_prompts = VISUAL_TUNING_V3_TEMPLATES
        selected_neg = VISUAL_TUNING_V3_NEGATIVE_PROMPT
    elif args.prompt_set == "visual_tuning_v2":
        selected_prompts = VISUAL_TUNING_V2_TEMPLATES
        selected_neg = VISUAL_TUNING_V2_NEGATIVE_PROMPT
    elif args.prompt_set == "prompt_tuning":
        selected_prompts = PROMPT_TUNING_TEMPLATES
        selected_neg = PROMPT_TUNING_NEGATIVE_PROMPT
    else:
        selected_prompts = BASELINE_PROMPT_TEMPLATES
        selected_neg = BASELINE_NEGATIVE_PROMPT

    candidates_map = {
        "sd15": {
            "id": "stable-diffusion-v1-5/stable-diffusion-v1-5",
            "vae": None,
        },
        "realistic_vision": {
            "id": "SG161222/Realistic_Vision_V5.1_noVAE",
            "vae": "stabilityai/sd-vae-ft-mse",
        },
    }

    c = candidates_map[args.candidate]

    # Pre-run programmatic token validation
    if args.prompt_set == "visual_tuning_v3_1":
        from transformers import CLIPTokenizer
        tok = CLIPTokenizer.from_pretrained(c["id"], subfolder="tokenizer")
        for idx, p in enumerate(selected_prompts, 1):
            p_len = len(tok(p)["input_ids"])
            assert p_len <= 65, f"ERROR: Prompt {idx} token count ({p_len}) exceeds target <= 65!"
        neg_len = len(tok(selected_neg)["input_ids"])
        assert neg_len <= 75, f"ERROR: Negative prompt token count ({neg_len}) exceeds target <= 75!"
        print(f"Pre-run token check passed: all positive prompts <= 65 tokens, negative prompt = {neg_len} tokens <= 75.")

    try:
        res = run_candidate_benchmark(
            candidate_id=c["id"],
            vae_id=c["vae"],
            image_size=args.image_size,
            num_inference_steps=args.steps,
            low_vram_mode=args.low_vram,
            prompt_templates=selected_prompts,
            negative_prompt=selected_neg,
            output_dir=reports_dir,
        )
    except Exception as e:
        print(f"ERROR running benchmark for {c['id']}: {e}")
        res = {"candidate": c["id"], "error": str(e), "speed_passed": False, "vram_passed": False}

    cand_report_file = reports_dir / f"benchmark_report_{args.candidate}.json"
    with open(cand_report_file, "w") as f:
        json.dump(res, f, indent=2)
    summary_file = reports_dir / "benchmark_report.json"
    with open(summary_file, "w") as f:
        json.dump([res], f, indent=2)
    print(f"\nCandidate {args.candidate} benchmark results saved to: {cand_report_file} and {summary_file}")



if __name__ == "__main__":
    main()
