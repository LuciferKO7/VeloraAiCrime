"""
Resumable Synthetic Dataset Generator for Suspect Facial Composites.
Adheres to:
- MASTER_PROMPT.md §11 Step A8 (Synthetic training set, T1)
- Resumable checkpointing via JSON ledger
- Safe deterministic pseudo-random sampling
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from PIL import Image

from ml_service.app.pipelines.attribute_verifier import ATTRIBUTE_ENUM_REGISTRY
from ml_service.app.pipelines.sketch_prompts import build_facial_composite_prompt
from ml_service.app.pipelines.upscaler import portrait_finalizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("velora.synth_faces")


class SyntheticCorpusGenerator:
    """Generates paired synthetic facial attributes, prompts, and sketches with resumable state."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.repo_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = output_dir or (self.repo_root / "training" / "synth_faces" / "data")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.output_dir.parent / "checkpoint.json"

    def load_checkpoint(self) -> Dict[str, Any]:
        """Loads generation state from disk if exists."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not read checkpoint file, starting fresh: %s", str(e))
        return {"last_index": -1, "total_generated": 0, "sample_ids": []}

    def save_checkpoint(self, last_index: int, total_generated: int, sample_ids: List[str]) -> None:
        """Persists generation state to disk atomically."""
        data = {
            "last_index": last_index,
            "total_generated": total_generated,
            "sample_ids": sample_ids,
        }
        temp_file = self.checkpoint_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.checkpoint_file)

    def sample_synthetic_attributes(self, seed: int) -> Dict[str, Any]:
        """Samples a diverse, unbiased combination of attributes from ATTRIBUTE_ENUM_REGISTRY."""
        rng = np.random.default_rng(seed)
        sampled = {}

        core_attributes = [
            "sex_presentation",
            "age_band",
            "appearance_group",
            "face_shape",
            "skin_tone",
            "hair_length",
            "hair_style",
            "hair_color",
            "eye_shape",
            "eye_color",
            "nose_bridge",
            "lips_fullness",
            "facial_hair_type",
            "glasses",
        ]

        for attr in core_attributes:
            choices = ATTRIBUTE_ENUM_REGISTRY.get(attr, [])
            if choices:
                val = choices[rng.integers(0, len(choices))]
                sampled[attr] = {"value": val}

        return sampled

    def generate_corpus(
        self,
        count: int = 10,
        base_seed: int = 10000,
        render_images: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Generates synthetic corpus items.
        If render_images=False, generates paired attribute-prompt metadata and sample placeholder canvas.
        """
        checkpoint = self.load_checkpoint()
        start_idx = checkpoint["last_index"] + 1
        sample_ids = list(checkpoint.get("sample_ids", []))
        generated_records: List[Dict[str, Any]] = []

        logger.info("Resuming corpus generation from index %d (target: %d)", start_idx, count)

        for i in range(start_idx, count):
            sample_seed = base_seed + i
            sample_id = f"synth_face_{i:06d}"

            attrs = self.sample_synthetic_attributes(sample_seed)
            prompt = build_facial_composite_prompt(attrs)

            # Create sample image
            img_path = self.output_dir / f"{sample_id}.png"
            json_path = self.output_dir / f"{sample_id}.json"

            if render_images:
                try:
                    from ml_service.app.core.config import settings
                    from ml_service.app.models.manager import model_manager
                    from ml_service.app.pipelines.sketch_prompts import SKETCH_NEGATIVE_PROMPT
                    import torch
                    pipe = model_manager.load_pipeline(
                        model_id=settings.DEFAULT_MODEL_ID,
                        vae_id=settings.DEFAULT_VAE_ID,
                        lcm_lora_id=settings.DEFAULT_LCM_LORA_ID,
                    )
                    use_cpu = model_manager.low_vram_mode or "cuda" not in model_manager.device
                    generator = torch.Generator(device="cpu" if use_cpu else "cuda").manual_seed(sample_seed)
                    res = pipe(
                        prompt=prompt,
                        negative_prompt=SKETCH_NEGATIVE_PROMPT,
                        width=512,
                        height=512,
                        num_inference_steps=3,
                        guidance_scale=1.5,
                        generator=generator,
                    )
                    img = res.images[0]
                except Exception as e:
                    logger.warning("Pipeline render failed for %s, falling back: %s", sample_id, str(e))
                    img = Image.new("RGB", (256, 256), color=(240, 240, 240))
            else:
                img = Image.new("RGB", (256, 256), color=(240, 240, 240))

            img.save(img_path)
            sha256_hex = portrait_finalizer.compute_sha256(img)

            record = {
                "sample_id": sample_id,
                "index": i,
                "seed": sample_seed,
                "attributes": attrs,
                "prompt": prompt,
                "image_path": str(img_path),
                "sha256": sha256_hex,
            }

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

            sample_ids.append(sample_id)
            generated_records.append(record)
            self.save_checkpoint(last_index=i, total_generated=len(sample_ids), sample_ids=sample_ids)

        logger.info("Corpus generation complete: %d items registered", len(sample_ids))
        return generated_records


if __name__ == "__main__":
    generator = SyntheticCorpusGenerator()
    generator.generate_corpus(count=5)
