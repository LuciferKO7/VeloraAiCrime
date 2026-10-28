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

PROMPT_TEMPLATES = [
    "front portrait photo of a 35 year old man, short black hair, studio lighting, neutral background",
    "front portrait photo of a 28 year old woman, long wavy hair, oval face, neutral lighting",
    "front portrait photo of a 45 year old man, round face, thick mustache, short dark hair",
    "front portrait photo of a 30 year old woman, square jawline, fair skin, straight black hair",
    "front portrait photo of a 50 year old man, receding hairline, thin eyebrows, brown eyes",
    "front portrait photo of a 22 year old person, wheatish skin tone, pointed chin, dark brown eyes",
]

SEEDS = [42, 101, 2024, 777]

NEGATIVE_PROMPT = (
    "cartoon, illustration, deformed, extra fingers, watermark, text, blurry, "
    "low quality, multiple faces, hat"
)


def create_contact_sheet(images: list[Image.Image], cols: int = 6, thumb_size: int = 256) -> Image.Image:
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
    output_dir: Path | None = None,
) -> dict:
    from diffusers import AutoencoderKL, LCMScheduler, StableDiffusionPipeline

    print(f"\n========================================================")
    print(f"BENCHMARKING CANDIDATE: {candidate_id}")
    print(f"VAE: {vae_id or 'default'} | LCM-LoRA: {lcm_lora_id}")
    print(f"Resolution: {image_size}x{image_size} | Steps: {num_inference_steps} | Low VRAM: {low_vram_mode}")
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
        prompt="front portrait photo of a person, studio lighting",
        negative_prompt=NEGATIVE_PROMPT,
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

    print(f"Running benchmark across {len(PROMPT_TEMPLATES)} prompts x {len(SEEDS)} seeds = 24 images...")
    img_counter = 0
    for p_idx, prompt in enumerate(PROMPT_TEMPLATES, 1):
        for s_idx, seed in enumerate(SEEDS, 1):
            img_counter += 1
            generator = torch.Generator(device="cpu" if low_vram_mode else "cuda").manual_seed(seed)
            torch.cuda.synchronize()
            t0 = time.perf_counter()

            result = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT,
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
        sheet = create_contact_sheet(generated_images, cols=6, thumb_size=256)
        sheet_path = output_dir / f"contact_sheet_{safe_name}.png"
        sheet.save(sheet_path)
        print(f"  Contact Sheet:  {sheet_path}")

    # Unload pipeline
    del pipe
    if vae:
        del vae
    torch.cuda.empty_cache()

    return {
        "candidate": candidate_id,
        "vae": vae_id,
        "lcm_lora": lcm_lora_id,
        "image_size": image_size,
        "steps": num_inference_steps,
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
    parser.add_argument("--output-dir", type=str, default="ml_service/reports", help="Reports directory")
    args = parser.parse_args()

    reports_dir = Path(args.output_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        {
            "id": "stable-diffusion-v1-5/stable-diffusion-v1-5",
            "vae": None,
        },
        {
            "id": "SG161222/Realistic_Vision_V5.1_noVAE",
            "vae": "stabilityai/sd-vae-ft-mse",
        },
    ]

    all_results = []
    for c in candidates:
        try:
            res = run_candidate_benchmark(
                candidate_id=c["id"],
                vae_id=c["vae"],
                image_size=args.image_size,
                num_inference_steps=args.steps,
                low_vram_mode=args.low_vram,
                output_dir=reports_dir,
            )
            all_results.append(res)
        except Exception as e:
            print(f"ERROR running benchmark for {c['id']}: {e}")
            all_results.append({"candidate": c["id"], "error": str(e), "speed_passed": False, "vram_passed": False})

    summary_file = reports_dir / "benchmark_report.json"
    with open(summary_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nAll benchmark results saved to: {summary_file}")


if __name__ == "__main__":
    main()
