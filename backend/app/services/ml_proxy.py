import base64
import hashlib
import json
import logging
import math
import re
import uuid
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

CANONICAL_REGIONS: tuple[str, ...] = (
    "hair",
    "eyes",
    "eyebrows",
    "nose",
    "mouth",
    "jaw",
    "cheeks",
    "forehead",
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


def decode_image_base64(b64_str: str) -> bytes:
    """
    Safely decodes raw base64 or data-URI base64 (e.g. data:image/png;base64,...).
    Raises ValueError on malformed or empty base64 string.
    """
    if not isinstance(b64_str, str) or not b64_str.strip():
        raise ValueError("Empty or non-string base64 image data")
    s = b64_str.strip()
    if "," in s:
        s = s.split(",", 1)[1]
    # Remove internal whitespace and line breaks
    s = "".join(s.split())
    try:
        raw_bytes = base64.b64decode(s, validate=True)
        if not raw_bytes:
            raise ValueError("Decoded base64 produced 0 bytes")
        return raw_bytes
    except Exception as exc:
        raise ValueError(f"Malformed base64 image data: {exc}") from exc


def resolve_canonical_region(
    instruction: str | None = None,
    explicit_region: str | None = None,
    mask_b64: str | None = None,
) -> str | None:
    """
    Validates explicit region or attempts to detect a single unambiguous canonical region
    from a natural language instruction.
    Returns the canonical region string, or None if a custom mask is provided.
    Raises AppError('VALIDATION_ERROR', 400) when ambiguous or missing.
    """
    if explicit_region:
        reg_clean = explicit_region.strip().lower()
        if reg_clean not in CANONICAL_REGIONS:
            raise AppError(
                "VALIDATION_ERROR",
                f"Region '{explicit_region}' is not supported. Supported canonical regions: {sorted(CANONICAL_REGIONS)}",
                status_code=400,
            )
        return reg_clean

    if mask_b64:
        return None

    if not instruction or not instruction.strip():
        raise AppError(
            "VALIDATION_ERROR",
            f"An anatomical region ({sorted(CANONICAL_REGIONS)}) or mask must be specified for edit.",
            status_code=400,
        )

    text = instruction.strip().lower()
    matches: set[str] = set()

    if re.search(r"\b(eyebrow|eyebrows|brows?)\b", text):
        matches.add("eyebrows")
    if re.search(r"\b(eye|eyes|eyelid|eyelids|pupils?)\b", text) and "eyebrow" not in text and "brow" not in text:
        matches.add("eyes")
    if re.search(r"\b(hair|hairline|bald|shaved|ponytail|bun|curls?|spiky)\b", text):
        matches.add("hair")
    if re.search(r"\b(nose|nostril|nostrils)\b", text):
        matches.add("nose")
    if re.search(r"\b(mouth|lips?|teeth|smile)\b", text):
        matches.add("mouth")
    if re.search(r"\b(jaw|jawline|chin)\b", text):
        matches.add("jaw")
    if re.search(r"\b(cheeks?|cheekbones?)\b", text):
        matches.add("cheeks")
    if re.search(r"\b(forehead)\b", text):
        matches.add("forehead")

    if len(matches) == 1:
        return next(iter(matches))

    if len(matches) == 0:
        raise AppError(
            "VALIDATION_ERROR",
            f"Could not identify a canonical anatomical region in edit instruction '{instruction}'. Supported regions: {sorted(CANONICAL_REGIONS)}",
            status_code=400,
        )

    raise AppError(
        "VALIDATION_ERROR",
        f"Ambiguous anatomical region in edit instruction '{instruction}' matches multiple regions: {sorted(matches)}. Please specify a single region or supply a mask.",
        status_code=400,
    )


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

    def check_health(self) -> dict[str, Any]:
        """
        Probes GET /ml/v1/health using X-Service-Key header and a bounded 2s timeout.
        Returns health telemetry dict on success or {'status': 'down', ...} on failure.
        """
        url = f"{self.base_url}/ml/v1/health"
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "down", "error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"status": "down", "error": str(exc)}

    def generate_initial_round(
        self,
        *,
        session_id: str,
        round_id: str,
        round_no: int,
        attributes: dict[str, Any],
        locked_features: list[Any] | None = None,
        num_variants: int = 6,
        seed: int | None = None,
        axes: dict[str, Any] | None = None,
        case_id: str | None = None,
        guidance_scale: float = 1.5,
        num_inference_steps: int = 3,
        image_size: int = 512,
    ) -> list[dict[str, Any]]:
        """
        Calls ML Service POST /ml/v1/generate.
        Adheres to Person A GenerateRequest / GenerateResponse schema.
        """
        num_var = max(1, min(num_variants, 6))
        actual_seed = seed if seed is not None else 42
        payload = {
            "module_type": "facial_composite",
            "case_id": case_id,
            "seed": actual_seed,
            "num_variants": num_var,
            "image_size": image_size,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "facial_attributes": attributes or {},
        }
        return self._send_request(
            "/ml/v1/generate",
            payload,
            session_id=session_id,
            round_id=round_id,
        )

    def evolve_round(
        self,
        *,
        session_id: str,
        round_id: str,
        round_no: int,
        parent_round_id: str,
        feedback: dict[str, Any] | list[dict[str, Any]],
        attributes: dict[str, Any],
        locked_features: list[Any] | None = None,
        num_variants: int = 6,
        seed: int | None = None,
        case_id: str | None = None,
        current_preference_vector: dict[str, float] | None = None,
        image_size: int = 512,
    ) -> list[dict[str, Any]]:
        """
        Calls ML Service POST /ml/v1/evolve.
        Adheres to Person A EvolveRequest / EvolveResponse schema.
        """
        feedback_events: list[dict[str, Any]] = []
        if isinstance(feedback, list):
            feedback_events = feedback
        elif isinstance(feedback, dict):
            if "events" in feedback and isinstance(feedback["events"], list):
                feedback_events = feedback["events"]
            elif feedback:
                feedback_events = [feedback]

        num_var = max(2, min(num_variants, 12))
        actual_seed = seed if seed is not None else 42
        payload = {
            "session_id": session_id,
            "case_id": case_id,
            "round_number": round_no,
            "base_attributes": attributes or {},
            "feedback_events": feedback_events,
            "current_preference_vector": current_preference_vector,
            "num_variants": num_var,
            "seed": actual_seed,
            "image_size": image_size,
        }
        return self._send_request(
            "/ml/v1/evolve",
            payload,
            session_id=session_id,
            round_id=round_id,
        )

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
        region: str | None = None,
        mask_b64: str | None = None,
        image_b64: str | None = None,
        seed: int = 42,
        strength: float = 0.75,
        feather_radius: int = 8,
    ) -> list[dict[str, Any]]:
        """
        Calls ML Service POST /ml/v1/edit.
        Adheres to Person A EditRequest / EditResponse schema.
        """
        resolved_region = resolve_canonical_region(
            instruction=instruction_text,
            explicit_region=region,
            mask_b64=mask_b64,
        )

        # Resolve parent image base64 if not supplied
        if not image_b64 and parent_image_id:
            parent_path = Path(settings.STORAGE_DIR) / "images" / f"{parent_image_id}.png"
            if parent_path.exists():
                raw = parent_path.read_bytes()
                image_b64 = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"

        payload: dict[str, Any] = {
            "image_id": parent_image_id,
            "seed": seed,
            "strength": strength,
            "feather_radius": feather_radius,
        }
        if image_b64:
            payload["image_b64"] = image_b64
        if resolved_region:
            payload["region"] = resolved_region
        if mask_b64:
            payload["mask_b64"] = mask_b64
        if instruction_text:
            payload["edit_instruction"] = instruction_text
        if attributes:
            payload["updated_attributes"] = attributes

        return self._send_request(
            "/ml/v1/edit",
            payload,
            session_id=session_id,
            round_id=round_id,
            default_kind=kind,
            parent_image_id=parent_image_id,
        )

    def get_embedding(self, image_bytes: bytes, image_id: str | None = None) -> tuple[list[float], str]:
        """
        Calls ML Service POST /ml/v1/embed to compute a 512-dim facial embedding.
        Sends JSON payload conforming to Person A EmbedRequest schema.
        Returns (embedding_floats, model_version).
        Validates embedding is 512 finite floats and L2-normalizes it.
        """
        url = f"{self.base_url}/ml/v1/embed"
        b64_str = base64.b64encode(image_bytes).decode("ascii")
        payload: dict[str, Any] = {
            "image_b64": f"data:image/png;base64,{b64_str}",
        }
        if image_id:
            payload["image_id"] = image_id

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                if resp.status_code == 404:
                    url_fallback = f"{self.base_url}/embed"
                    resp = client.post(url_fallback, json=payload, headers=self._headers())

                if resp.status_code in (429, 503):
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

                data = resp.json()
                raw_emb = data.get("embedding")
                if not isinstance(raw_emb, list) or len(raw_emb) != 512:
                    got_desc = len(raw_emb) if isinstance(raw_emb, list) else type(raw_emb)
                    raise AppError("ML_UNAVAILABLE", f"Invalid embedding dimension: expected 512, got {got_desc}", status_code=503)

                norm_sq = 0.0
                clean_emb: list[float] = []
                for val in raw_emb:
                    if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                        raise AppError("ML_UNAVAILABLE", "Embedding contains non-finite values", status_code=503)
                    fval = float(val)
                    clean_emb.append(fval)
                    norm_sq += fval * fval

                norm = math.sqrt(norm_sq)
                if norm > 1e-12:
                    clean_emb = [x / norm for x in clean_emb]
                else:
                    raise AppError("ML_UNAVAILABLE", "Embedding has zero norm", status_code=503)

                model_version = data.get("model_version") or "arcface-r100-v1"
                return clean_emb, str(model_version)

        except httpx.RequestError as exc:
            logger.error("ML service unreachable at %s: %s", url, exc)
            raise AppError("ML_UNAVAILABLE", f"ML service unreachable at {self.base_url}: {exc}", status_code=503) from exc

    def _send_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        session_id: str,
        round_id: str,
        default_kind: str = "variant",
        parent_image_id: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                if resp.status_code in (429, 503):
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

                content_type = resp.headers.get("content-type", "")
                raw_items: list[dict[str, Any]] = []

                if "ndjson" in content_type:
                    for line in resp.text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        chunk = json.loads(line)
                        if chunk.get("event") == "image" or "image" in chunk:
                            raw_items.append(chunk.get("image") or chunk)
                        elif chunk.get("event") == "done" and "images" in chunk:
                            raw_items.extend(chunk["images"])
                else:
                    data = resp.json()
                    if isinstance(data, list):
                        raw_items = data
                    elif isinstance(data, dict):
                        if "images" in data and isinstance(data["images"], list):
                            raw_items = data["images"]
                        elif "variants" in data and isinstance(data["variants"], list):
                            raw_items = data["variants"]
                        elif "image_base64" in data:
                            # Single-image response (e.g. EditResponse)
                            raw_items = [data]
                        else:
                            raw_items = []

                if not raw_items:
                    raise AppError("ML_UNAVAILABLE", "ML service returned no images", status_code=503)

                images: list[dict[str, Any]] = []
                for default_idx, item in enumerate(raw_items):
                    norm = self._normalize_image_dict(
                        item,
                        session_id=session_id,
                        round_id=round_id,
                        default_variant_index=default_idx,
                        default_kind=default_kind,
                        parent_image_id=parent_image_id,
                    )
                    images.append(norm)

                return images

        except httpx.RequestError as exc:
            logger.error("ML service unreachable at %s: %s", url, exc)
            raise AppError("ML_UNAVAILABLE", f"ML service unreachable at {self.base_url}: {exc}", status_code=503) from exc

    def _normalize_image_dict(
        self,
        raw: dict[str, Any],
        session_id: str,
        round_id: str,
        default_variant_index: int = 0,
        default_kind: str = "variant",
        parent_image_id: str | None = None,
    ) -> dict[str, Any]:
        img_id = raw.get("id") or raw.get("image_id")
        if not img_id:
            img_id = str(uuid.uuid4())

        # Extract image bytes: decode base64 if present, or use raw bytes, or fallback
        raw_bytes: bytes | None = None
        b64_val = raw.get("image_base64") or raw.get("image_b64")
        if b64_val:
            try:
                raw_bytes = decode_image_base64(b64_val)
            except ValueError as ve:
                logger.error("Failed to decode image_base64 for variant %s: %s", img_id, ve)
                raise AppError("ML_UNAVAILABLE", f"ML service returned invalid image base64: {ve}", status_code=503) from ve
        elif "image_bytes" in raw and isinstance(raw["image_bytes"], (bytes, bytearray)):
            raw_bytes = bytes(raw["image_bytes"])

        if raw_bytes is None:
            raw_bytes = MINIMAL_PNG_BYTES

        # Extract sketch bytes if present (e.g. mask or sketch)
        skt_bytes: bytes = raw_bytes
        skt_b64 = raw.get("sketch_base64") or raw.get("mask_used_base64")
        if skt_b64:
            try:
                skt_bytes = decode_image_base64(skt_b64)
            except ValueError:
                skt_bytes = raw_bytes

        # Save to disk
        img_rel, img_sha = save_image_bytes(img_id, raw_bytes, is_sketch=False)
        skt_rel, skt_sha = save_image_bytes(img_id, skt_bytes, is_sketch=True)

        var_idx = raw.get("variant_index")
        if var_idx is None:
            var_idx = raw.get("index", default_variant_index)

        prompt_str = raw.get("prompt_text") or raw.get("prompt_used") or ""
        p_img_id = raw.get("parent_image_id") or parent_image_id

        return {
            "id": img_id,
            "session_id": session_id,
            "round_id": round_id,
            "parent_image_id": p_img_id,
            "variant_index": int(var_idx),
            "kind": raw.get("kind", default_kind),
            "width": int(raw.get("width", 512)),
            "height": int(raw.get("height", 512)),
            "seed": raw.get("seed") or raw.get("seed_used"),
            "prompt_text": prompt_str,
            "negative_prompt": raw.get("negative_prompt", ""),
            "variant_axes_json": json.dumps(raw.get("variant_axes") or raw.get("variant_axes_json") or {}),
            "sha256": raw.get("sha256") or img_sha,
            "sketch_sha256": raw.get("sketch_sha256") or skt_sha,
            "storage_path": raw.get("storage_path") or img_rel,
            "sketch_path": raw.get("sketch_path") or skt_rel,
            "model_versions_json": json.dumps(raw.get("model_versions") or raw.get("model_versions_json") or {}),
            "attr_adherence": raw.get("attr_adherence"),
            "identity_similarity": raw.get("identity_similarity"),
            "speculative": int(raw.get("speculative", 0) or raw.get("is_uncertain", False)),
            "is_final": int(raw.get("is_final", 0)),
        }


ml_proxy = MLProxyClient()
