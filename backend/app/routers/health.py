from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.core.config import settings
from backend.app.db.session import get_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(conn: Connection = Depends(get_connection)):
    # Check DB
    db_status = "error"
    try:
        conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    # Real connection check with 2s timeout for ml_service
    ml_status = "down"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ML_SERVICE_URL}/health")
            if resp.status_code in (200, 401):
                ml_status = "ok"
    except Exception:
        ml_status = "down"

    # Real connection check with 2s timeout for speech_service
    speech_status = "down"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.SPEECH_SERVICE_URL}/health")
            if resp.status_code in (200, 401):
                speech_status = "ok"
    except Exception:
        speech_status = "down"

    now_iso = datetime.now(UTC).isoformat()
    overall = "ok" if db_status == "ok" else "degraded"

    return {
        "status": overall,
        "db": db_status,
        "ml_service": ml_status,
        "speech_service": speech_status,
        "llm": {
            "gemini": "configured" if settings.GEMINI_API_KEY else "unconfigured",
            "ollama": "configured" if settings.OLLAMA_URL else "unconfigured",
        },
        "time": now_iso,
    }
