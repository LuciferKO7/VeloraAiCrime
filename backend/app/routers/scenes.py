"""Scenes router for spatial investigative crime scene reconstruction.
Exposes router for automatic discovery per §3 architecture.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone

from ..services.scene.builder import DEFAULT_EMPTY_SCENE, validate_scene_data

router = APIRouter(prefix="/api/v1", tags=["scenes"])

class SceneSaveRequest(BaseModel):
    session_id: str
    case_id: str
    title: Optional[str] = "Scene Diagram"
    scene: Dict[str, Any]

@router.get("/sessions/{session_id}/scene")
async def get_session_scene(
    session_id: str,
    x_access_purpose: Optional[str] = Header(None, alias="X-Access-Purpose"),
):
    """Retrieve the scene graph for a given session."""
    if not x_access_purpose or len(x_access_purpose.strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "PURPOSE_REQUIRED", "message": "Access purpose minimum 5 characters required"}}
        )

    return {
        "id": f"scene-{session_id}",
        "session_id": session_id,
        "title": "Investigative Scene Layout",
        "scene": DEFAULT_EMPTY_SCENE,
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

@router.put("/sessions/{session_id}/scene")
async def update_session_scene(
    session_id: str,
    req: SceneSaveRequest,
    x_access_purpose: Optional[str] = Header(None, alias="X-Access-Purpose"),
):
    """Update scene diagram data."""
    if not x_access_purpose or len(x_access_purpose.strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "PURPOSE_REQUIRED", "message": "Access purpose minimum 5 characters required"}}
        )

    if not validate_scene_data(req.scene):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Scene data failed schema validation"}}
        )

    return {
        "id": f"scene-{session_id}",
        "session_id": session_id,
        "title": req.title,
        "version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
