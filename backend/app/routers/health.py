from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.deps import require_role
from backend.app.core.config import settings
from backend.app.db.session import get_connection
from backend.app.llm.providers.gemini import call_gemini
from backend.app.llm.providers.ollama import call_ollama

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


@router.get("/health/llm-live")
def llm_live_check(current_user: dict = Depends(require_role("admin"))):
    """
    Live LLM provider connectivity check (§8.1, TB3.2).
    Requires admin role.
    Performs live probe to Gemini and Ollama and reports actual connectivity and latency.
    Never exposes secrets or credentials in output.
    """
    gemini_res: dict[str, Any] = {
        "ok": False,
        "latency_ms": None,
        "model": settings.GEMINI_MODEL_FAST or "gemini-2.5-flash",
        "error": None,
    }
    ollama_res: dict[str, Any] = {
        "ok": False,
        "latency_ms": None,
        "model": settings.OLLAMA_MODEL or "qwen2.5:3b-instruct",
        "error": None,
    }

    # 1. Test Gemini
    if not settings.GEMINI_API_KEY:
        gemini_res["error"] = "GEMINI_API_KEY is not configured"
    else:
        try:
            _, _, _, lat_ms = call_gemini(
                model=gemini_res["model"],
                system="",
                user="ping",
                temperature=0.0,
                timeout_s=5.0,
            )
            gemini_res["ok"] = True
            gemini_res["latency_ms"] = lat_ms
        except Exception as exc:
            gemini_res["ok"] = False
            gemini_res["error"] = str(exc)

    # 2. Test Ollama
    if not settings.OLLAMA_URL:
        ollama_res["error"] = "OLLAMA_URL is not configured"
    else:
        try:
            _, _, _, lat_ms = call_ollama(
                model=ollama_res["model"],
                system="",
                user="ping",
                temperature=0.0,
                timeout_s=5.0,
            )
            ollama_res["ok"] = True
            ollama_res["latency_ms"] = lat_ms
        except Exception as exc:
            ollama_res["ok"] = False
            ollama_res["error"] = str(exc)

    return {
        "gemini": gemini_res,
        "ollama": ollama_res,
    }
