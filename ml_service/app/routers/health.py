"""
Health and telemetry endpoint for Velora ML Service.
Endpoint: GET /ml/v1/health
"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ml_service.app.core.auth import verify_service_key
from ml_service.app.core.config import settings
from ml_service.app.models.manager import model_manager

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model for service health check."""

    status: str = Field("ok", description="Service readiness status")
    service: str = Field("ml_service", description="Service identifier")
    version: str = Field("1.0.0", description="Contract version")
    cuda_available: bool = Field(..., description="Whether CUDA is available to PyTorch")
    device: str = Field(..., description="Active compute device")
    gpu_name: Optional[str] = Field(None, description="Physical GPU device name")
    vram_total_mb: float = Field(..., description="Total device VRAM in MiB")
    vram_allocated_mb: float = Field(..., description="Currently allocated VRAM in MiB")
    vram_reserved_mb: float = Field(..., description="Currently reserved VRAM in MiB")
    low_vram_mode: bool = Field(..., description="Whether sequential offload low-VRAM mode is active")
    active_model: Optional[str] = Field(None, description="Currently loaded pipeline identifier")
    disclaimer: str = Field(..., description="Mandatory responsible AI disclaimer")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="ML Service Health & VRAM Telemetry",
    dependencies=[Depends(verify_service_key)],
)
async def get_health() -> HealthResponse:
    """
    Returns real hardware metrics, active pipeline state, and VRAM budget.
    Protected by service-to-service authentication (X-Service-Key).
    """
    mem_status = model_manager.get_memory_status()

    return HealthResponse(
        status="ok",
        service="ml_service",
        version="1.0.0",
        cuda_available=mem_status["cuda_available"],
        device=mem_status["device"],
        gpu_name=mem_status["gpu_name"],
        vram_total_mb=mem_status["vram_total_mb"],
        vram_allocated_mb=mem_status["vram_allocated_mb"],
        vram_reserved_mb=mem_status["vram_reserved_mb"],
        low_vram_mode=mem_status["low_vram_mode"],
        active_model=mem_status["active_model"],
        disclaimer=settings.DISCLAIMER_V1,
    )
