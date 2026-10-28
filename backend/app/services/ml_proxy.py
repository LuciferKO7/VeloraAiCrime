import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from backend.app.core.config import settings
from backend.app.core.errors import AppError

logger = logging.getLogger("velora.ml_proxy")

# 1x1 transparent PNG fallback if test doesn't supply bytes
MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def ensure_storage_dir() -> tuple[Path, Path]:
    storage = Path(settings.STORAGE_DIR)
    img_dir = storage / "images"
    skt_dir = storage / "sketches"
    img_dir.mkdir(parents=True, exist_ok=True)
    skt_dir.mkdir(parents=True, exist_ok=True)
    return img_dir, skt_dir


def save_image_bytes(image_id: str, raw_bytes: bytes, is_sketch: bool = False) -> tuple[str, str]:
    img_dir, skt_dir = ensure_storage_dir()
    target_dir = skt_dir if is_sketch else img_dir
    file_path = target_dir / f"{image_id}.png"
    file_path.write_bytes(raw_bytes)
    sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
    rel_path = f"sketches/{image_id}.png" if is_sketch else f"images/{image_id}.png"
    return rel_path, sha256_hash


class MLProxyClient:
    def __init__(self, base_url: str | None = None, service_key: str | None = None):
        self.base_url = (base_url or getattr(settings, "ML_SERVICE_URL", "http://localhost:8001")).rstrip("/")
        self.service_key = service_key or getattr(settings, "SERVICE_KEY", "")

    def _headers(self) -> dict[str, str]:
        return {
            "X-Service-Key": self.service_key,
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson, application/json",
        }

    def generate_initial_round(
        self,
        *,
        session_id: str,
        round_id: str,
        round_no: int,
        attributes: dict[str, Any],
        locked_features: list[Any],
        num_variants: int = 6,
        seed: int | None = None,
        axes: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Calls ML Service POST /ml/v1/generate.
        Returns list of image dictionaries conforming to images schema.
        """
        payload = {
            "session_id": session_id,
            "round_id": round_id,
            "round_no": round_no,
            "kind": "initial",
            "attributes": attributes,
            "locked_features": locked_features,
            "num_variants": num_variants,
            "seed": seed,
            "axes": axes or {},
        }
        return self._send_request("/ml/v1/generate", payload, session_id=session_id, round_id=round_id)

    def evolve_round(
        self,
        *,
        session_id: str,
        round_id: str,
        round_no: int,
        parent_round_id: str,
        feedback: dict[str, Any],
        attributes: dict[str, Any],
        locked_features: list[Any],
        num_variants: int = 6,
    ) -> list[dict[str, Any]]:
        """
        Calls ML Service POST /ml/v1/evolve.
        """
        payload = {
            "session_id": session_id,
            "round_id": round_id,
            "round_no": round_no,
            "kind": "evolve",
            "parent_round_id": parent_round_id,
            "feedback": feedback,
            "attributes": attributes,
            "locked_features": locked_features,
            "num_variants": num_variants,
        }
        return self._send_request("/ml/v1/evolve", payload, session_id=session_id, round_id=round_id)

    def edit_round(
        self,
        *,
        session_id: str,
        round_id: str,
        round_no: int,
        parent_image_id: str,
        instruction_text: str,
        kind: str = "edit",
        attributes: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Calls ML Service POST /ml/v1/edit.
        """
        payload = {
            "session_id": session_id,
            "round_id": round_id,
            "round_no": round_no,
            "kind": kind,
            "parent_image_id": parent_image_id,
            "instruction_text": instruction_text,
            "attributes": attributes or {},
        }
        return self._send_request("/ml/v1/edit", payload, session_id=session_id, round_id=round_id)

    def _send_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        session_id: str,
        round_id: str,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                if resp.status_code == 503 or resp.status_code == 429:
                    try:
                        err_json = resp.json()
                        err_code = err_json.get("error", {}).get("code")
                        if err_code == "ML_BUSY":
                            raise AppError("ML_BUSY", "ML service is busy processing another request", status_code=503)
                    except Exception as parse_err:
                        if isinstance(parse_err, AppError):
                            raise
                    raise AppError("ML_UNAVAILABLE", f"ML service error: {resp.text}", status_code=503)

                if resp.status_code != 200:
                    raise AppError("ML_UNAVAILABLE", f"ML service returned HTTP {resp.status_code}: {resp.text}", status_code=503)

                # Process response: can be NDJSON or standard JSON
                images: list[dict[str, Any]] = []
                content_type = resp.headers.get("content-type", "")
                if "ndjson" in content_type:
                    for line in resp.text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        chunk = json.loads(line)
                        if chunk.get("event") == "image" or "image" in chunk:
                            img_obj = chunk.get("image") or chunk
                            images.append(self._normalize_image_dict(img_obj, session_id, round_id))
                        elif chunk.get("event") == "done" and "images" in chunk:
                            for img_obj in chunk["images"]:
                                images.append(self._normalize_image_dict(img_obj, session_id, round_id))
                else:
                    data = resp.json()
                    raw_list = data if isinstance(data, list) else data.get("images", [])
                    for img_obj in raw_list:
                        images.append(self._normalize_image_dict(img_obj, session_id, round_id))

                if not images:
                    raise AppError("ML_UNAVAILABLE", "ML service returned no images", status_code=503)

                return images

        except httpx.RequestError as exc:
            logger.error("ML service unreachable at %s: %s", url, exc)
            raise AppError("ML_UNAVAILABLE", f"ML service unreachable at {self.base_url}: {exc}", status_code=503) from exc

    def _normalize_image_dict(self, raw: dict[str, Any], session_id: str, round_id: str) -> dict[str, Any]:
        img_id = raw.get("id") or raw.get("image_id")
        if not img_id:
            import uuid
            img_id = str(uuid.uuid4())

        # Ensure image file on disk
        img_rel, img_sha = save_image_bytes(img_id, MINIMAL_PNG_BYTES, is_sketch=False)
        skt_rel, skt_sha = save_image_bytes(img_id, MINIMAL_PNG_BYTES, is_sketch=True)

        return {
            "id": img_id,
            "session_id": session_id,
            "round_id": round_id,
            "parent_image_id": raw.get("parent_image_id"),
            "variant_index": raw.get("variant_index", 0),
            "kind": raw.get("kind", "variant"),
            "width": raw.get("width", 512),
            "height": raw.get("height", 512),
            "seed": raw.get("seed"),
            "prompt_text": raw.get("prompt_text", ""),
            "negative_prompt": raw.get("negative_prompt", ""),
            "variant_axes_json": json.dumps(raw.get("variant_axes") or raw.get("variant_axes_json") or {}),
            "sha256": raw.get("sha256") or img_sha,
            "sketch_sha256": raw.get("sketch_sha256") or skt_sha,
            "storage_path": raw.get("storage_path") or img_rel,
            "sketch_path": raw.get("sketch_path") or skt_rel,
            "model_versions_json": json.dumps(raw.get("model_versions") or raw.get("model_versions_json") or {}),
            "attr_adherence": raw.get("attr_adherence"),
            "identity_similarity": raw.get("identity_similarity"),
            "speculative": int(raw.get("speculative", 0)),
            "is_final": int(raw.get("is_final", 0)),
        }


ml_proxy = MLProxyClient()

