import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import get_current_user
from backend.app.core.errors import AppError
from backend.app.db.session import get_connection
from backend.app.services.speech_proxy import SpeechProxyClient, save_audio_bytes

logger = logging.getLogger("velora.routers.speech")

router = APIRouter(prefix="/speech", tags=["speech"])


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_lang: str = Field(..., pattern="^(en|ta|hi|te|kn|ml|bn|mr)$")
    target_lang: str = Field(default="en", pattern="^(en|ta|hi|te|kn|ml|bn|mr)$")


@router.post("/transcribe")
async def transcribe_audio(
    request: Request,
    language_hint: str | None = Query(None),
    case_id: str | None = Query(None),
    session_id: str | None = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
    conn: Connection = Depends(get_connection),
):
    """
    Transcribes audio payload via the speech service.
    Accepts raw audio bytes or JSON with audio_base64.
    Computes and stores audio SHA-256 and writes a speech.transcribe audit record.
    """
    if language_hint and language_hint not in ("en", "ta", "hi", "te", "kn", "ml", "bn", "mr"):
        raise AppError("VALIDATION_ERROR", f"Unsupported language hint '{language_hint}'", status_code=422)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            raw_b64 = body.get("audio_base64") or body.get("audio") or ""
            audio_bytes = base64.b64decode(raw_b64)
            if not language_hint:
                language_hint = body.get("language_hint") or body.get("language")
        except Exception as exc:
            raise AppError("VALIDATION_ERROR", "Invalid JSON or audio_base64 payload", status_code=400) from exc
    else:
        audio_bytes = await request.body()

    if not audio_bytes:
        raise AppError("VALIDATION_ERROR", "Audio payload is empty", status_code=400)

    # Save audio and compute SHA-256
    rel_path, audio_sha = save_audio_bytes(audio_bytes, suffix=".wav")

    proxy = SpeechProxyClient()
    transcription = proxy.transcribe(
        audio_bytes=audio_bytes,
        filename="audio.wav",
        language_hint=language_hint,
    )

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    purpose = request.headers.get("x-access-purpose", "Audio statement transcription")

    write_audit_entry(
        conn,
        action="speech.transcribe",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        resource_type="speech_audio",
        resource_id=audio_sha,
        case_id=case_id,
        purpose=purpose,
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={
            "session_id": session_id,
            "audio_sha256": audio_sha,
            "detected_language": transcription.get("language"),
            "audio_path": rel_path,
            "duration_s": transcription.get("duration_s"),
        },
    )

    return {
        "text": transcription["text"],
        "language": transcription["language"],
        "audio_sha256": audio_sha,
        "duration_s": transcription.get("duration_s"),
    }


@router.post("/translate")
def translate_text_endpoint(
    body: TranslateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """
    Translates text between supported regional languages and English via IndicTrans2.
    """
    proxy = SpeechProxyClient()
    result = proxy.translate(
        text=body.text,
        source_lang=body.source_lang,
        target_lang=body.target_lang,
    )
    return result
