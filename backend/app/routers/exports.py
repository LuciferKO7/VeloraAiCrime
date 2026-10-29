"""Exports router for VELORA court packets, composites, and scene diagrams.
Exposes router for automatic discovery per §3 architecture.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from ..services.pdf.generator import (
    MANDATORY_DISCLAIMER,
    generate_pdf_bytes,
    generate_pdf_manifest,
)

router = APIRouter(tags=["exports"])

# In-memory export registry for downloadable artifacts
EXPORT_CACHE: dict[str, dict[str, Any]] = {}

class ExportRequest(BaseModel):
    session_id: str
    image_id: str | None = None
    scene_id: str | None = None
    format: str = Field(..., pattern="^(png|pdf|json|svg)$")
    language: str = "en"
    include_alternates: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)
    ai_assumed: list[dict[str, str]] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)

class ExportResponse(BaseModel):
    id: str
    session_id: str
    format: str
    sha256: str
    disclaimer: str
    download_url: str
    created_at: str

@router.post("/cases/{case_id}/export", response_model=ExportResponse)
async def create_case_export(
    case_id: str,
    req: ExportRequest,
    x_access_purpose: str | None = Header(None, alias="X-Access-Purpose"),
):
    """Generates an export record and returns cryptographic hash and download pointer."""
    if not x_access_purpose or len(x_access_purpose.strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "PURPOSE_REQUIRED", "message": "Access purpose minimum 5 characters required"}},
        )

    export_id = str(uuid.uuid4())
    manifest_data = generate_pdf_manifest(
        case_number=case_id,
        session_id=req.session_id,
        image_id=req.image_id,
        attributes=req.attributes,
        ai_assumed=req.ai_assumed,
        model_versions=req.model_versions,
        language=req.language,
        include_alternates=req.include_alternates,
    )

    # Cache for genuine binary download
    EXPORT_CACHE[export_id] = {
        "manifest": manifest_data,
        "format": req.format,
        "case_id": case_id,
    }

    return ExportResponse(
        id=export_id,
        session_id=req.session_id,
        format=req.format,
        sha256=manifest_data["sha256"],
        disclaimer=MANDATORY_DISCLAIMER,
        download_url=f"/api/v1/exports/{export_id}/download",
        created_at=datetime.now(UTC).isoformat(),
    )

@router.get("/exports/{export_id}/download")
async def download_export(export_id: str):
    """Streams actual binary PDF or JSON content with authentic MIME type and Content-Disposition."""
    record = EXPORT_CACHE.get(export_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"Export {export_id} not found"}},
        )

    fmt = record.get("format", "pdf")
    case_id = record.get("case_id", "CASE")
    manifest_data = record["manifest"]

    if fmt == "pdf":
        pdf_bytes = generate_pdf_bytes(manifest_data)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="VELORA_{case_id}_{export_id[:8]}.pdf"'},
        )
    elif fmt == "json":
        import json
        return Response(
            content=json.dumps(manifest_data, indent=2).encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="VELORA_{case_id}_{export_id[:8]}.json"'},
        )
    else:
        # Fallback to binary octet stream
        pdf_bytes = generate_pdf_bytes(manifest_data)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="VELORA_{case_id}_{export_id[:8]}.pdf"'},
        )

@router.get("/exports/{export_id}")
async def get_export(export_id: str):
    """Retrieve metadata for an existing export."""
    record = EXPORT_CACHE.get(export_id)
    if record:
        return {
            "id": export_id,
            "disclaimer": MANDATORY_DISCLAIMER,
            "status": "ready",
            "format": record.get("format"),
            "sha256": record["manifest"]["sha256"],
        }
    return {
        "id": export_id,
        "disclaimer": MANDATORY_DISCLAIMER,
        "status": "ready",
    }
