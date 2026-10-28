import hashlib
import logging
from pathlib import Path
from typing import Any

import httpx

from backend.app.core.config import settings
from backend.app.core.errors import AppError

logger = logging.getLogger("velora.speech_proxy")


def ensure_audio_storage() -> Path:
    storage = Path(settings.STORAGE_DIR)
    audio_dir = storage / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def save_audio_bytes(raw_bytes: bytes, suffix: str = ".wav") -> tuple[str, str]:
    audio_dir = ensure_audio_storage()
    sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
    file_path = audio_dir / f"{sha256_hash}{suffix}"
    if not file_path.exists():
        file_path.write_bytes(raw_bytes)
    rel_path = f"audio/{sha256_hash}{suffix}"
    return rel_path, sha256_hash


class SpeechProxyClient:
    def __init__(self, base_url: str | None = None, service_key: str | None = None, timeout_s: float = 10.0):
        self.base_url = (base_url or getattr(settings, "SPEECH_SERVICE_URL", "http://localhost:8002")).rstrip("/")
        self.service_key = service_key or getattr(settings, "SERVICE_KEY", "")
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {
            "X-Service-Key": self.service_key,
        }

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        Calls Speech Service POST /sp/v1/transcribe.
        Expects multipart/form-data.
        Returns dict containing text, language, and optional duration_s.
        """
        url = f"{self.base_url}/sp/v1/transcribe"
        files = {"audio": (filename, audio_bytes, "audio/wav")}
        data = {}
        if language_hint:
            data["language"] = language_hint

        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, files=files, data=data, headers=self._headers())
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.error("Speech service connection failed for transcribe: %s", exc)
            raise AppError("SPEECH_UNAVAILABLE", "Speech service is unreachable or timed out", status_code=503) from exc
        except Exception as exc:
            logger.error("Unexpected error contacting speech service: %s", exc)
            raise AppError("SPEECH_UNAVAILABLE", f"Speech service request failed: {exc}", status_code=503) from exc

        if resp.status_code == 503:
            raise AppError("SPEECH_UNAVAILABLE", "Speech service reported 503 unavailable", status_code=503)
        if resp.status_code >= 400:
            raise AppError("VALIDATION_ERROR", f"Speech service returned {resp.status_code}: {resp.text}", status_code=resp.status_code)

        result = resp.json()
        return {
            "text": result.get("text", "").strip(),
            "language": result.get("language") or result.get("detected_language") or language_hint or "en",
            "duration_s": result.get("duration_s") or result.get("duration"),
            "segments": result.get("segments", []),
        }

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str = "en",
    ) -> dict[str, Any]:
        """
        Calls Speech Service POST /sp/v1/translate.
        Expects JSON payload {"text": text, "source_lang": source_lang, "target_lang": target_lang}.
        Returns dict containing translated_text, source_lang, target_lang.
        """
        if source_lang == target_lang:
            return {
                "translated_text": text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "engine": "none",
            }

        url = f"{self.base_url}/sp/v1/translate"
        payload = {
            "text": text,
            "source_lang": source_lang,
            "target_lang": target_lang,
        }
        headers = self._headers()
        headers["Content-Type"] = "application/json"

        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, json=payload, headers=headers)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.error("Speech service connection failed for translate: %s", exc)
            raise AppError("SPEECH_UNAVAILABLE", "Speech service is unreachable or timed out", status_code=503) from exc
        except Exception as exc:
            logger.error("Unexpected error contacting speech service for translate: %s", exc)
            raise AppError("SPEECH_UNAVAILABLE", f"Speech service request failed: {exc}", status_code=503) from exc

        if resp.status_code == 503:
            raise AppError("SPEECH_UNAVAILABLE", "Speech service reported 503 unavailable", status_code=503)
        if resp.status_code >= 400:
            raise AppError("VALIDATION_ERROR", f"Speech service translate returned {resp.status_code}: {resp.text}", status_code=resp.status_code)

        result = resp.json()
        translated = result.get("translated_text") or result.get("text") or ""
        return {
            "translated_text": translated.strip(),
            "source_lang": source_lang,
            "target_lang": target_lang,
            "engine": "indictrans2",
        }

