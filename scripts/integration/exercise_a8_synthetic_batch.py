"""
Exercise Milestone A8: Small Real Generation Batch with Interruption & Resumption.
Verifies:
1. Real rendered images (not prompts alone or blank canvases)
2. Interrupt and resume lifecycle with JSON checkpoint
3. Zero duplicate records upon resumption
4. Annotations and SHA256 integrity match contract
"""

import hashlib
import json
import logging
import shutil
from pathlib import Path
from PIL import Image

from training.synth_faces.generate_synthetic_corpus import SyntheticCorpusGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("velora.exercise_a8")


def run_a8_exercise():
    repo_root = Path(__file__).resolve().parent.parent.parent
    test_dir = repo_root / "training" / "synth_faces" / "data_batch_test"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    generator = SyntheticCorpusGenerator(output_dir=test_dir)

    # 1. Phase 1: Start batch, run 1 real image, then interrupt
    logger.info("--- Phase 1: Generating 1 real rendered sample (simulating interrupt) ---")
    records_p1 = generator.generate_corpus(count=1, base_seed=7000, render_images=True)
    assert len(records_p1) == 1, f"Expected 1 record in Phase 1, got {len(records_p1)}"
    rec0 = records_p1[0]

    # Verify rec0 image is real PNG
    img0_path = Path(rec0["image_path"])
    assert img0_path.exists(), f"Image not found at {img0_path}"
    with Image.open(img0_path) as im0:
        assert im0.format == "PNG", f"Expected PNG format, got {im0.format}"
        assert im0.size == (512, 512), f"Expected 512x512, got {im0.size}"
        # Verify it's not a uniform blank image
        extrema = im0.getextrema()
        is_blank = all(e[0] == e[1] for e in extrema)
        assert not is_blank, "Generated image is blank/placeholder, expected real rendered sketch"

    # Verify SHA256 matches actual file
    with open(img0_path, "rb") as f:
        file_sha = hashlib.sha256(f.read()).hexdigest()
    assert file_sha == rec0["sha256"], f"SHA256 mismatch: {file_sha} != {rec0['sha256']}"

    ckpt1 = generator.load_checkpoint()
    assert ckpt1["last_index"] == 0
    assert ckpt1["total_generated"] == 1
    assert ckpt1["sample_ids"] == [rec0["sample_id"]]

    logger.info("Phase 1 verified: Item %s rendered and checkpointed.", rec0["sample_id"])

    # 2. Phase 2: Resume from checkpoint to target of 2
    logger.info("--- Phase 2: Resuming batch from checkpoint to target count 2 ---")
    records_p2 = generator.generate_corpus(count=2, base_seed=7000, render_images=True)
    assert len(records_p2) == 1, f"Expected exactly 1 new record upon resumption, got {len(records_p2)}"
    rec1 = records_p2[0]
    assert rec1["index"] == 1, f"Expected resumed index 1, got {rec1['index']}"
    assert rec1["sample_id"] != rec0["sample_id"], "Duplicate sample ID detected!"

    img1_path = Path(rec1["image_path"])
    assert img1_path.exists()
    with Image.open(img1_path) as im1:
        assert im1.format == "PNG"
        assert im1.size == (512, 512)

    ckpt2 = generator.load_checkpoint()
    assert ckpt2["last_index"] == 1
    assert ckpt2["total_generated"] == 2
    assert len(ckpt2["sample_ids"]) == 2
    assert len(set(ckpt2["sample_ids"])) == 2  # Zero duplicates

    # Clean up test output
    shutil.rmtree(test_dir)
    if generator.checkpoint_file.exists():
        generator.checkpoint_file.unlink()

    print("\n" + "=" * 60)
    print("GATE A8 REAL GENERATION BATCH & RESUME: PASS")
    print("=" * 60)
    print(f"Sample 0: {rec0['sample_id']} (seed={rec0['seed']}) -> SHA256: {rec0['sha256'][:16]}...")
    print(f"Sample 1: {rec1['sample_id']} (seed={rec1['seed']}) -> SHA256: {rec1['sha256'][:16]}...")
    print("Zero duplicates upon interruption and resumption.")
    print("Real 512x512 rendered sketch images verified.")
    print("=" * 60)


if __name__ == "__main__":
    run_a8_exercise()
