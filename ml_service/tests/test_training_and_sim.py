"""
Unit tests for Milestones A8 (Synthetic Corpus), A9 (Bias Audit), and A10 (Convergence Simulation).
Covers:
- SyntheticCorpusGenerator attribute sampling, prompt building, and resumable checkpoint persistence
- DemographicBiasAuditor disparate impact calculation (DIR >= 0.80 four-fifths rule) and disparity flagging
- WitnessConvergenceSimulator multi-round preference convergence and distance reduction
"""

import shutil
from pathlib import Path
import pytest
import numpy as np

from training.synth_faces.generate_synthetic_corpus import SyntheticCorpusGenerator
from training.verifier.bias_audit import DemographicBiasAuditor
from training.sim.convergence_sim import WitnessConvergenceSimulator


# ============================================================================
# 1. A8: Synthetic Corpus Generator Tests
# ============================================================================
def test_synthetic_corpus_sampling():
    """Verify that synthetic attribute sampling produces valid non-empty attribute sets."""
    gen = SyntheticCorpusGenerator()
    attrs = gen.sample_synthetic_attributes(seed=123)
    assert len(attrs) >= 10
    assert "sex_presentation" in attrs
    assert "age_band" in attrs
    assert "hair_length" in attrs
    assert isinstance(attrs["sex_presentation"]["value"], str)


def test_synthetic_corpus_resumable_checkpoint(tmp_path):
    """Verify that corpus generation saves checkpoints and resumes cleanly without duplicate IDs."""
    test_dir = tmp_path / "test_synth_data"
    gen = SyntheticCorpusGenerator(output_dir=test_dir)

    # First run: generate 3 items (indices 0, 1, 2)
    records_1 = gen.generate_corpus(count=3, base_seed=5000)
    assert len(records_1) == 3
    assert gen.checkpoint_file.exists()

    ckpt = gen.load_checkpoint()
    assert ckpt["last_index"] == 2
    assert ckpt["total_generated"] == 3

    # Second run: request total of 5 items (should resume from index 3 and generate 2 more)
    records_2 = gen.generate_corpus(count=5, base_seed=5000)
    assert len(records_2) == 2
    assert records_2[0]["index"] == 3
    assert records_2[1]["index"] == 4

    ckpt_final = gen.load_checkpoint()
    assert ckpt_final["last_index"] == 4
    assert ckpt_final["total_generated"] == 5
    assert len(ckpt_final["sample_ids"]) == 5
    assert len(set(ckpt_final["sample_ids"])) == 5  # Zero duplicates


# ============================================================================
# 2. A9: Demographic Bias Auditor Tests
# ============================================================================
def test_bias_auditor_balanced_parity_pass():
    """Verify that balanced group adherence passes four-fifths parity rule (DIR >= 0.80)."""
    auditor = DemographicBiasAuditor()
    # Balanced groups: means range between 0.81 and 0.86 (DIR = 0.81 / 0.86 = 0.94 >= 0.80)
    balanced_scores = {
        "south_asian": [0.85, 0.86, 0.84],
        "east_asian": [0.83, 0.85, 0.84],
        "southeast_asian": [0.84, 0.84, 0.85],
        "white": [0.86, 0.85, 0.87],
        "black": [0.82, 0.83, 0.84],
        "middle_eastern": [0.84, 0.85, 0.83],
        "latino": [0.83, 0.84, 0.85],
    }

    report = auditor.evaluate_group_adherence(balanced_scores)
    assert report["parity_passed"] is True
    assert report["status"] == "PASS"
    assert report["disparate_impact_ratio"] >= 0.80


def test_bias_auditor_disparate_impact_flagged():
    """Verify that severely disparate groups trigger FLAGGED_DISPARATE_IMPACT."""
    auditor = DemographicBiasAuditor()
    # Unbalanced: one group at 0.50 while another is at 0.90 (DIR = 0.50 / 0.90 = 0.55 < 0.80)
    skewed_scores = {
        "south_asian": [0.90, 0.92],
        "east_asian": [0.88, 0.90],
        "southeast_asian": [0.89, 0.88],
        "white": [0.91, 0.90],
        "black": [0.50, 0.52],  # Severe under-performance
        "middle_eastern": [0.88, 0.89],
        "latino": [0.89, 0.90],
    }

    report = auditor.evaluate_group_adherence(skewed_scores)
    assert report["parity_passed"] is False
    assert report["status"] == "FLAGGED_DISPARATE_IMPACT"
    assert report["disparate_impact_ratio"] < 0.80


def test_bias_auditor_synthetic_run():
    """Verify full synthetic bias audit execution and report writing."""
    auditor = DemographicBiasAuditor()
    rep = auditor.run_synthetic_bias_audit(num_samples_per_group=10, seed=777)
    assert "disparate_impact_ratio" in rep
    assert "group_metrics" in rep
    assert len(rep["group_metrics"]) == len(auditor.groups)
    assert rep["parity_passed"] is True
    assert "disclaimer" in rep


def test_bias_auditor_missing_group_insufficient_data():
    """Verify that missing demographic groups are reported honestly as INSUFFICIENT_EVALUATION_DATA."""
    auditor = DemographicBiasAuditor()
    partial_scores = {
        "south_asian": [0.85, 0.86],
        "east_asian": [0.84, 0.85],
        # Remaining groups missing
    }
    report = auditor.evaluate_group_adherence(partial_scores)
    assert report["evidence_sufficient"] is False
    assert report["status"] == "INSUFFICIENT_EVALUATION_DATA"
    assert "black" in report["missing_groups"]
    assert report["group_metrics"]["black"]["sample_count"] == 0
    assert report["group_metrics"]["black"]["mean_adherence"] is None


def test_bias_auditor_zero_denominator_safe():
    """Verify division-by-zero protection when maximum mean is zero."""
    auditor = DemographicBiasAuditor()
    zero_scores = {grp: [0.0, 0.0] for grp in auditor.groups}
    report = auditor.evaluate_group_adherence(zero_scores)
    assert report["disparate_impact_ratio"] == 0.0
    assert report["parity_passed"] is False


# ============================================================================
# 3. A10: Witness Convergence Simulator Tests
# ============================================================================
def test_convergence_simulator_distance_reduction():
    """Verify that multi-round selection loop reduces Euclidean distance to target."""
    sim = WitnessConvergenceSimulator(learning_rate=0.45)
    # Target feature vector
    target = {
        "jaw_prominence": 0.70,
        "eye_openness": -0.60,
        "lip_fullness": 0.50,
        "forehead_height": -0.40,
        "cheek_fullness": 0.60,
        "hair_volume": -0.50,
        "age_progression": 0.40,
    }

    rep = sim.run_simulation(target_features=target, num_rounds=6, seed=42)

    assert rep["converged"] is True
    assert rep["status"] == "PASS"
    assert rep["final_distance"] < rep["initial_distance"]
    assert rep["distance_reduction_pct"] > 20.0
    assert rep["final_cosine_similarity"] > 0.60

    # Verify history trace length
    assert len(rep["round_history"]) == 6
