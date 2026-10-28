"""
Configuration settings for Velora ML Service.
Adheres to MASTER_PROMPT.md §2 (GPU budgeting), §4 (.env.example), and §6.3 (conventions).
"""

import os
from pathlib import Path
from typing import Optional
import torch


class Settings:
    """Application settings with environment variable support and secret masking."""

    def __init__(self):
        self.APP_ENV: str = os.getenv("APP_ENV", "development")
        self.HOST: str = os.getenv("ML_HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("ML_PORT", "8001"))

        # Service-to-service authentication
        self.SERVICE_KEY: str = os.getenv("SERVICE_KEY", "dev-service-key-change-in-prod")

        # Directories
        self.REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
        self.ML_MODELS_DIR: Path = Path(os.getenv("ML_MODELS_DIR", str(self.REPO_ROOT / "ml_service" / "models")))
        self.ML_STORAGE_DIR: Path = Path(os.getenv("ML_STORAGE_DIR", str(self.REPO_ROOT / "ml_service" / "storage")))

        # Device and VRAM Management
        cuda_available = torch.cuda.is_available()
        default_device = "cuda" if cuda_available else "cpu"
        self.ML_DEVICE: str = os.getenv("ML_DEVICE", default_device)

        # Low VRAM mode calculation:
        # If explicitly set, obey; otherwise auto-detect based on GPU memory (< 6.0 GB)
        low_vram_env = os.getenv("LOW_VRAM_MODE", "auto").lower()
        if low_vram_env in ("true", "1", "yes"):
            self.LOW_VRAM_MODE: bool = True
        elif low_vram_env in ("false", "0", "no"):
            self.LOW_VRAM_MODE: bool = False
        else:
            # Auto: True if GPU has < 6.0 GB total VRAM or on CPU fallback
            if cuda_available:
                total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                self.LOW_VRAM_MODE: bool = total_gb < 6.0
            else:
                self.LOW_VRAM_MODE: bool = True

        # Pipeline Parameters
        self.ML_IMAGE_SIZE: int = int(os.getenv("ML_IMAGE_SIZE", "512"))
        self.ML_VARIANT_STEPS: int = int(os.getenv("ML_VARIANT_STEPS", "3"))

        # Frozen Model Identifiers (Candidate 2 verified stack)
        self.DEFAULT_MODEL_ID: str = "SG161222/Realistic_Vision_V5.1_noVAE"
        self.DEFAULT_VAE_ID: str = "stabilityai/sd-vae-ft-mse"
        self.DEFAULT_LCM_LORA_ID: str = "latent-consistency/lcm-lora-sdv1-5"

        # Responsible AI Invariant Constant (§6.3)
        self.DISCLAIMER_V1: str = "AI-generated investigative aid — not a photograph, not evidence of identity."

    def __repr__(self) -> str:
        masked_key = "***" if self.SERVICE_KEY else ""
        return (
            f"Settings(ENV={self.APP_ENV}, HOST={self.HOST}:{self.PORT}, "
            f"DEVICE={self.ML_DEVICE}, LOW_VRAM={self.LOW_VRAM_MODE}, "
            f"SERVICE_KEY={masked_key})"
        )


settings = Settings()
