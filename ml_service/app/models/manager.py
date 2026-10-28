"""
ModelManager: VRAM lifecycle and pipeline orchestration for Velora ML Service.
Adheres to MASTER_PROMPT.md §2 (GPU budgeting):
- Maximum one SD-1.5-class generative pipeline in VRAM at any time (LRU swap).
- Automatic sequential CPU offloading in LOW_VRAM_MODE.
- Explicit memory reclamation via gc and torch.cuda.empty_cache().
"""

import gc
import logging
import sys
import threading
from typing import Any, Dict, Optional
import torch

try:
    import safetensors.torch
    if sys.platform == "win32":
        _orig_safetensors_load = safetensors.torch.load_file
        def _safe_safetensors_load(filename, device="cpu", backend="pread"):
            return _orig_safetensors_load(filename, device=device, backend=backend)
        safetensors.torch.load_file = _safe_safetensors_load
except Exception:
    pass

from ml_service.app.core.config import settings

logger = logging.getLogger("velora.ml.manager")


class ModelManager:
    """Manages ML pipeline lifecycle, GPU memory constraints, and model swapping."""

    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ModelManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.device = settings.ML_DEVICE
        self.low_vram_mode = settings.LOW_VRAM_MODE
        self.active_model_id: Optional[str] = None
        self.active_vae_id: Optional[str] = None
        self.active_lora_id: Optional[str] = None
        self._pipeline: Optional[Any] = None
        self._pipeline_lock = threading.Lock()
        self._initialized = True

        logger.info(
            "ModelManager initialized: device=%s, low_vram_mode=%s",
            self.device,
            self.low_vram_mode,
        )

    def get_memory_status(self) -> Dict[str, Any]:
        """Query real GPU VRAM metrics without mock data."""
        cuda_avail = torch.cuda.is_available()
        status: Dict[str, Any] = {
            "cuda_available": cuda_avail,
            "device": self.device,
            "low_vram_mode": self.low_vram_mode,
            "active_model": self.active_model_id,
            "gpu_name": None,
            "vram_total_mb": 0.0,
            "vram_allocated_mb": 0.0,
            "vram_reserved_mb": 0.0,
        }

        if cuda_avail and "cuda" in self.device:
            props = torch.cuda.get_device_properties(0)
            status["gpu_name"] = props.name
            status["vram_total_mb"] = round(props.total_memory / (1024**2), 1)
            status["vram_allocated_mb"] = round(torch.cuda.memory_allocated() / (1024**2), 1)
            status["vram_reserved_mb"] = round(torch.cuda.memory_reserved() / (1024**2), 1)

        return status

    def unload_active_model(self) -> None:
        """Evicts active pipeline from VRAM, cleans CUDA cache and garbage collector."""
        with self._pipeline_lock:
            if self._pipeline is not None:
                logger.info("Evicting active pipeline from VRAM: %s", self.active_model_id)
                del self._pipeline
                self._pipeline = None
                self.active_model_id = None
                self.active_vae_id = None
                self.active_lora_id = None

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            logger.debug("VRAM cache cleared successfully.")

    def load_pipeline(
        self,
        model_id: str,
        vae_id: Optional[str] = None,
        lcm_lora_id: Optional[str] = None,
    ) -> Any:
        """
        Loads the requested pipeline with LRU single-model VRAM discipline.
        If a different model is active, unloads it before loading the new one.
        """
        with self._pipeline_lock:
            # Check if matching pipeline is already loaded
            if (
                self._pipeline is not None
                and self.active_model_id == model_id
                and self.active_vae_id == vae_id
                and self.active_lora_id == lcm_lora_id
            ):
                logger.debug("Reusing already loaded pipeline: %s", model_id)
                return self._pipeline

            # Unload any previously loaded pipeline first (Single-model VRAM invariant)
            if self._pipeline is not None:
                logger.info("Swapping pipeline: unloading %s to load %s", self.active_model_id, model_id)
                del self._pipeline
                self._pipeline = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            logger.info("Loading generative pipeline: model=%s, vae=%s, lora=%s", model_id, vae_id, lcm_lora_id)

            from diffusers import AutoencoderKL, LCMScheduler, StableDiffusionPipeline

            # Load custom VAE if specified
            vae = None
            if vae_id:
                vae = AutoencoderKL.from_pretrained(
                    vae_id,
                    torch_dtype=torch.float16 if "cuda" in self.device else torch.float32,
                )

            pipe = StableDiffusionPipeline.from_pretrained(
                model_id,
                vae=vae,
                torch_dtype=torch.float16 if "cuda" in self.device else torch.float32,
                safety_checker=None,
            )

            # Fuse LCM LoRA and set scheduler
            if lcm_lora_id:
                pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
                pipe.load_lora_weights(lcm_lora_id)
                pipe.fuse_lora()

            # Apply memory-management strategy based on LOW_VRAM_MODE
            if self.low_vram_mode and "cuda" in self.device:
                pipe.enable_sequential_cpu_offload()
            elif "cuda" in self.device:
                pipe.to("cuda")
                pipe.enable_attention_slicing()

            self._pipeline = pipe
            self.active_model_id = model_id
            self.active_vae_id = vae_id
            self.active_lora_id = lcm_lora_id

            logger.info("Pipeline loaded successfully: %s", model_id)
            return self._pipeline

    @property
    def is_loaded(self) -> bool:
        """Returns True if a generative pipeline is currently active in memory."""
        return self._pipeline is not None


model_manager = ModelManager()
