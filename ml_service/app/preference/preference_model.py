"""
Online Preference Model for Witness Facial Evolution.
Adheres to:
- MASTER_PROMPT.md §1 D1 (Recognition-first variant grid with online preference model)
- MASTER_PROMPT.md §11 Step A5 (Preference model and /evolve)
- contracts/schema.sql (variant_axes_json and feedback_events)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("velora.ml.preference_model")

# Continuous variation axes calibrated for forensic facial recognition
RECOGNITION_AXES: List[str] = [
    "jaw_prominence",    # Narrow/tapered (-1.0) to Broad/square (+1.0)
    "eye_openness",      # Narrow/hooded (-1.0) to Wide/round (+1.0)
    "lip_fullness",      # Thin/taut (-1.0) to Full/plump (+1.0)
    "forehead_height",   # Low hairline (-1.0) to High forehead (+1.0)
    "cheek_fullness",    # Hollow/sunken (-1.0) to Full/round (+1.0)
    "hair_volume",       # Flat/close-cropped (-1.0) to Voluminous/thick (+1.0)
    "age_progression",   # Younger (-1.0) to Older (+1.0)
]

AXIS_PROMPT_DESCRIPTORS: Dict[str, Tuple[str, str]] = {
    "jaw_prominence": ("narrow tapered jawline", "broad square jawline"),
    "eye_openness": ("narrow hooded eyes", "wide open alert eyes"),
    "lip_fullness": ("thin narrow lips", "full prominent lips"),
    "forehead_height": ("low forehead", "tall broad forehead"),
    "cheek_fullness": ("hollow lean cheeks", "full rounded cheeks"),
    "hair_volume": ("flat low-volume hair", "thick voluminous hair"),
    "age_progression": ("youthful features", "aged weathered features with subtle character lines"),
}


class OnlinePreferenceModel:
    """
    Maintains an online Bayesian-style feature preference state across feedback rounds.
    Balances exploration (early rounds) with exploitation/convergence (later rounds).
    """

    def __init__(self, axes: Optional[List[str]] = None, learning_rate: float = 0.35):
        self.axes = axes or list(RECOGNITION_AXES)
        self.num_axes = len(self.axes)
        self.learning_rate = learning_rate

    def init_preference_vector(self) -> Dict[str, float]:
        """Returns a neutral initial preference vector (all zeros)."""
        return {axis: 0.0 for axis in self.axes}

    def update_preference_vector(
        self,
        current_vector: Dict[str, float],
        feedback_events: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """
        Updates preference weights based on witness feedback events:
        - 'select' / 'like': positive delta
        - 'dislike': negative delta
        - 'dismiss': neutral / mild negative delta
        """
        updated = dict(current_vector)

        for event in feedback_events:
            ev_type = event.get("event_type", "").lower()
            axes_data = event.get("variant_axes", {})
            if not axes_data:
                continue

            multiplier = 0.0
            if ev_type in ("select", "pick"):
                multiplier = 1.0
            elif ev_type == "like":
                multiplier = 0.6
            elif ev_type == "dislike":
                multiplier = -0.7
            elif ev_type == "dismiss":
                multiplier = -0.2

            for axis in self.axes:
                if axis in axes_data:
                    delta = float(axes_data[axis]) * multiplier * self.learning_rate
                    # Clamp to [-1.0, 1.0] range
                    updated[axis] = float(np.clip(updated.get(axis, 0.0) + delta, -1.0, 1.0))

        return updated

    def sample_round_variants(
        self,
        preference_vector: Dict[str, float],
        round_number: int = 1,
        num_variants: int = 6,
        seed: int = 42,
    ) -> List[Dict[str, float]]:
        """
        Samples N variant perturbation vectors for the next round.
        Exploration variance decays as 1 / sqrt(round_number) to enforce convergence.
        """
        rng = np.random.default_rng(seed)
        # Decay exploration variance over rounds (simulating genetic convergence)
        sigma = max(0.15, 0.65 / np.sqrt(max(1, round_number)))

        variants: List[Dict[str, float]] = []

        # Variant 0 is always the exploitation mode (current mean preference vector)
        mean_variant = {k: float(np.clip(v, -1.0, 1.0)) for k, v in preference_vector.items()}
        variants.append(mean_variant)

        # Remaining variants (1..N-1) explore perturbed directions along primary axes
        for idx in range(1, num_variants):
            sample = {}
            for axis in self.axes:
                mean_val = preference_vector.get(axis, 0.0)
                perturbation = rng.normal(loc=0.0, scale=sigma)
                sample[axis] = float(np.clip(mean_val + perturbation, -1.0, 1.0))
            variants.append(sample)

        return variants

    def build_variant_prompt_modifiers(self, variant_axes: Dict[str, float]) -> List[str]:
        """Translates numerical axis values into natural language sketch prompt modifiers."""
        # Sort by magnitude to prioritize most significant distinctive features and stay within CLIP 77 tokens
        sorted_axes = sorted(
            [(k, v) for k, v in variant_axes.items() if abs(v) >= 0.25 and k in AXIS_PROMPT_DESCRIPTORS],
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        modifiers: List[str] = []
        for axis, val in sorted_axes[:3]:
            neg_desc, pos_desc = AXIS_PROMPT_DESCRIPTORS[axis]
            modifiers.append(pos_desc if val > 0 else neg_desc)
        return modifiers


preference_model = OnlinePreferenceModel()
