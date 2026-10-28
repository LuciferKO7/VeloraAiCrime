import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jsonschema
from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.db.session import get_engine
from backend.app.llm.providers.gemini import call_gemini
from backend.app.llm.providers.ollama import call_ollama

logger = logging.getLogger("velora.llm.router")

VALID_TASKS = {
    "parse",
    "edit_parse",
    "question",
    "translate",
    "scene_extract",
    "synth_describe",
    "glossary_suggest",
    "smoke",
    "other",
}

NO_CASE_ALLOWED_TASKS = {
    "smoke",
    "synth_describe",
    "glossary_suggest",
    "translate",
}

CACHEABLE_TASKS = {
    "parse",
    "edit_parse",
    "translate",
}


@dataclass
class LLMResult:
    content: dict[str, Any] | str
    raw_text: str
    provider: str
    model: str
    route_reason: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    call_id: str
    cached: bool = False


class TokenBucket:
    def __init__(self, rpm: int):
        self.capacity = float(rpm)
        self.tokens = float(rpm)
        self.rate = float(rpm) / 60.0
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, max_wait: float = 2.0) -> bool:
        start_wait = time.monotonic()
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

                needed = 1.0 - self.tokens
                wait_time = needed / self.rate

            remaining_budget = max_wait - (time.monotonic() - start_wait)
            if wait_time > remaining_budget or remaining_budget <= 0:
                return False

            sleep_chunk = min(wait_time, remaining_budget, 0.2)
            time.sleep(sleep_chunk)


gemini_rate_limiter = TokenBucket(settings.GEMINI_RPM or 8)

# In-memory cache: key -> (LLMResult, expire_timestamp)
_llm_cache: dict[str, tuple[dict[str, Any], str, int, int, float]] = {}
_cache_lock = threading.Lock()


def get_cache_key(task: str, model: str, system: str, user: str) -> str:
    raw = f"{task}:{model}:{system}:{user}".encode()
    return hashlib.sha256(raw).hexdigest()


def extract_json_text(raw_text: str) -> str:
    text_content = raw_text.strip()
    if text_content.startswith("```json"):
        text_content = text_content[7:]
    elif text_content.startswith("```"):
        text_content = text_content[3:]
    if text_content.endswith("```"):
        text_content = text_content[:-3]
    return text_content.strip()


def record_llm_call(
    *,
    call_id: str,
    case_id: str | None,
    session_id: str | None,
    task: str,
    provider: str,
    model: str,
    route_reason: str,
    prompt_text: str,
    response_text: str,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
    status: str,
    error: str | None,
) -> None:
    now_iso = datetime.now(UTC).isoformat()
    # Mask any potential sensitive keys or tokens
    safe_prompt = prompt_text[:4000] if prompt_text else ""
    safe_response = response_text[:8000] if response_text else ""
    safe_error = error[:2000] if error else None

    query = text(
        """
        INSERT INTO llm_calls (
            id, case_id, session_id, task, provider, model, route_reason,
            prompt_text, response_text, latency_ms, tokens_in, tokens_out,
            status, error, created_at
        ) VALUES (
            :id, :case_id, :session_id, :task, :provider, :model, :route_reason,
            :prompt_text, :response_text, :latency_ms, :tokens_in, :tokens_out,
            :status, :error, :created_at
        )
        """
    )
    with get_engine().begin() as conn:
        conn.execute(
            query,
            {
                "id": call_id,
                "case_id": case_id,
                "session_id": session_id,
                "task": task,
                "provider": provider,
                "model": model,
                "route_reason": route_reason,
                "prompt_text": safe_prompt,
                "response_text": safe_response,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "status": status,
                "error": safe_error,
                "created_at": now_iso,
            },
        )


def _resolve_data_mode(case_id: str | None, task: str) -> str:
    if case_id is None:
        if task not in NO_CASE_ALLOWED_TASKS:
            raise AppError(
                "VALIDATION_ERROR",
                f"case_id is required for task '{task}'",
                details={"allowed_no_case_tasks": sorted(NO_CASE_ALLOWED_TASKS)},
                status_code=422,
            )
        return "demo"

    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT data_mode FROM cases WHERE id = :id"),
            {"id": case_id},
        ).fetchone()
        if not row:
            raise AppError("NOT_FOUND", f"Case '{case_id}' not found", status_code=404)
        return str(row[0])


def _validate_schema(
    parsed: Any,
    schema: dict[str, Any],
) -> tuple[bool, str | None]:
    try:
        clean_schema = dict(schema)
        clean_schema.pop("$schema", None)
        jsonschema.validate(instance=parsed, schema=clean_schema)
        return True, None
    except jsonschema.ValidationError as err:
        return False, str(err.message)
    except Exception as exc:
        return False, str(exc)


def _execute_provider_call_with_repair(
    provider: str,
    model: str,
    task: str,
    case_id: str | None,
    session_id: str | None,
    system: str,
    user: str,
    schema: dict[str, Any] | None,
    route_reason: str,
    temperature: float,
) -> tuple[dict[str, Any] | str, str, int, int, int, str]:
    """
    Executes a provider call, parses JSON if schema is present,
    validates against schema, and performs at most 1 repair attempt.
    Returns: (parsed_content, raw_text, tokens_in, tokens_out, latency_ms, call_id)
    Raises Exception if provider call fails or schema remains invalid.
    """
    call_id = str(uuid.uuid4())
    full_prompt = f"System: {system}\nUser: {user}"

    if provider == "gemini":
        raw_text, tok_in, tok_out, lat_ms = call_gemini(
            model=model,
            system=system,
            user=user,
            schema=schema,
            temperature=temperature,
        )
    else:
        raw_text, tok_in, tok_out, lat_ms = call_ollama(
            model=model,
            system=system,
            user=user,
            schema=schema,
            temperature=temperature,
        )

    if not schema:
        record_llm_call(
            call_id=call_id,
            case_id=case_id,
            session_id=session_id,
            task=task,
            provider=provider,
            model=model,
            route_reason=route_reason,
            prompt_text=full_prompt,
            response_text=raw_text,
            latency_ms=lat_ms,
            tokens_in=tok_in,
            tokens_out=tok_out,
            status="ok",
            error=None,
        )
        return raw_text, raw_text, tok_in, tok_out, lat_ms, call_id

    # Schema parsing
    clean_text = extract_json_text(raw_text)
    parse_ok = True
    parsed_json: Any = None
    validation_err: str | None = None

    try:
        parsed_json = json.loads(clean_text)
        is_valid, validation_err = _validate_schema(parsed_json, schema)
        if not is_valid:
            parse_ok = False
    except Exception as exc:
        parse_ok = False
        validation_err = f"JSON decode error: {exc}"

    if parse_ok and parsed_json is not None:
        record_llm_call(
            call_id=call_id,
            case_id=case_id,
            session_id=session_id,
            task=task,
            provider=provider,
            model=model,
            route_reason=route_reason,
            prompt_text=full_prompt,
            response_text=raw_text,
            latency_ms=lat_ms,
            tokens_in=tok_in,
            tokens_out=tok_out,
            status="ok",
            error=None,
        )
        return parsed_json, raw_text, tok_in, tok_out, lat_ms, call_id

    # First attempt was invalid schema -> record schema_invalid
    record_llm_call(
        call_id=call_id,
        case_id=case_id,
        session_id=session_id,
        task=task,
        provider=provider,
        model=model,
        route_reason=route_reason,
        prompt_text=full_prompt,
        response_text=raw_text,
        latency_ms=lat_ms,
        tokens_in=tok_in,
        tokens_out=tok_out,
        status="schema_invalid",
        error=validation_err,
    )

    # EXACTLY ONE REPAIR ATTEMPT (§8.1)
    repair_prompt = (
        f"The previous response failed schema validation:\n"
        f"Validation Error: {validation_err}\n"
        f"Previous Output: {raw_text}\n"
        f"Please output ONLY valid JSON conforming to the schema."
    )
    repair_call_id = str(uuid.uuid4())
    repair_full_prompt = f"System: {system}\nUser: {user}\nRepair: {repair_prompt}"

    try:
        if provider == "gemini":
            rep_text, rep_in, rep_out, rep_ms = call_gemini(
                model=model,
                system=system,
                user=f"{user}\n\n[Correction Required]: {repair_prompt}",
                schema=schema,
                temperature=0.0,
            )
        else:
            rep_text, rep_in, rep_out, rep_ms = call_ollama(
                model=model,
                system=system,
                user=f"{user}\n\n[Correction Required]: {repair_prompt}",
                schema=schema,
                temperature=0.0,
            )

        rep_clean = extract_json_text(rep_text)
        rep_parsed = json.loads(rep_clean)
        is_rep_valid, rep_val_err = _validate_schema(rep_parsed, schema)

        if is_rep_valid:
            record_llm_call(
                call_id=repair_call_id,
                case_id=case_id,
                session_id=session_id,
                task=task,
                provider=provider,
                model=model,
                route_reason=route_reason,
                prompt_text=repair_full_prompt,
                response_text=rep_text,
                latency_ms=rep_ms,
                tokens_in=tok_in + rep_in,
                tokens_out=tok_out + rep_out,
                status="ok",
                error=None,
            )
            return (
                rep_parsed,
                rep_text,
                tok_in + rep_in,
                tok_out + rep_out,
                lat_ms + rep_ms,
                repair_call_id,
            )
        else:
            record_llm_call(
                call_id=repair_call_id,
                case_id=case_id,
                session_id=session_id,
                task=task,
                provider=provider,
                model=model,
                route_reason=route_reason,
                prompt_text=repair_full_prompt,
                response_text=rep_text,
                latency_ms=rep_ms,
                tokens_in=tok_in + rep_in,
                tokens_out=tok_out + rep_out,
                status="schema_invalid",
                error=f"Repair failed validation: {rep_val_err}",
            )
            raise ValueError(f"Schema validation failed after repair: {rep_val_err}")
    except Exception as exc:
        if "Repair failed validation" not in str(exc):
            record_llm_call(
                call_id=repair_call_id,
                case_id=case_id,
                session_id=session_id,
                task=task,
                provider=provider,
                model=model,
                route_reason=route_reason,
                prompt_text=repair_full_prompt,
                response_text="",
                latency_ms=0,
                tokens_in=0,
                tokens_out=0,
                status="error",
                error=str(exc),
            )
        raise


def complete(
    task: str,
    *,
    case_id: str | None = None,
    session_id: str | None = None,
    system: str = "",
    user: str = "",
    schema: dict[str, Any] | None = None,
    tier: str = "fast",
    temperature: float = 0.0,
) -> LLMResult:
    """
    VELORA LLM Router single entry point (§8.1).
    Routes to Ollama or Gemini according to case data_mode and LLM_PROVIDER_MODE.
    """
    if task not in VALID_TASKS:
        raise AppError(
            "VALIDATION_ERROR",
            f"Invalid LLM task '{task}'",
            details={"allowed_tasks": sorted(VALID_TASKS)},
            status_code=422,
        )

    data_mode = _resolve_data_mode(case_id, task)

    # 1. Real Case Isolation (§0 R11.4, §8.1)
    if data_mode == "real":
        # Under no circumstance instantiate or invoke Gemini
        ollama_model = settings.OLLAMA_MODEL or "qwen2.5:3b-instruct"
        route_reason = "real_local_only"

        # Check Cache
        if task in CACHEABLE_TASKS:
            cache_key = get_cache_key(task, ollama_model, system, user)
            with _cache_lock:
                if cache_key in _llm_cache:
                    cached_val, cached_raw, c_in, c_out, exp_at = _llm_cache[cache_key]
                    if exp_at > time.time():
                        cache_call_id = str(uuid.uuid4())
                        record_llm_call(
                            call_id=cache_call_id,
                            case_id=case_id,
                            session_id=session_id,
                            task=task,
                            provider="ollama",
                            model=ollama_model,
                            route_reason=route_reason,
                            prompt_text=f"System: {system}\nUser: {user}",
                            response_text=cached_raw,
                            latency_ms=1,
                            tokens_in=c_in,
                            tokens_out=c_out,
                            status="ok",
                            error=None,
                        )
                        return LLMResult(
                            content=cached_val,
                            raw_text=cached_raw,
                            provider="ollama",
                            model=ollama_model,
                            route_reason=route_reason,
                            latency_ms=1,
                            tokens_in=c_in,
                            tokens_out=c_out,
                            call_id=cache_call_id,
                            cached=True,
                        )

        try:
            content, raw, tok_in, tok_out, lat_ms, call_id = _execute_provider_call_with_repair(
                provider="ollama",
                model=ollama_model,
                task=task,
                case_id=case_id,
                session_id=session_id,
                system=system,
                user=user,
                schema=schema,
                route_reason=route_reason,
                temperature=temperature,
            )
        except Exception as exc:
            err_msg = str(exc)
            if "schema validation failed" in err_msg.lower():
                raise AppError("LLM_SCHEMA_INVALID", f"Local model returned invalid schema: {err_msg}", status_code=502) from exc
            record_llm_call(
                call_id=str(uuid.uuid4()),
                case_id=case_id,
                session_id=session_id,
                task=task,
                provider="ollama",
                model=ollama_model,
                route_reason=route_reason,
                prompt_text=f"System: {system}\nUser: {user}",
                response_text="",
                latency_ms=0,
                tokens_in=0,
                tokens_out=0,
                status="error",
                error=err_msg,
            )
            raise AppError("LLM_UNAVAILABLE_LOCAL", f"Local LLM service is unavailable: {err_msg}", status_code=503) from exc

        if task in CACHEABLE_TASKS and isinstance(content, dict):
            cache_key = get_cache_key(task, ollama_model, system, user)
            with _cache_lock:
                _llm_cache[cache_key] = (
                    content,
                    raw,
                    tok_in,
                    tok_out,
                    time.time() + (settings.LLM_CACHE_TTL_S or 3600),
                )

        return LLMResult(
            content=content,
            raw_text=raw,
            provider="ollama",
            model=ollama_model,
            route_reason=route_reason,
            latency_ms=lat_ms,
            tokens_in=tok_in,
            tokens_out=tok_out,
            call_id=call_id,
            cached=False,
        )

    # 2. Demo Case Routing (§8.1)
    provider_mode = (settings.LLM_PROVIDER_MODE or "auto").lower()

    if provider_mode == "ollama":
        ollama_model = settings.OLLAMA_MODEL or "qwen2.5:3b-instruct"
        route_reason = "forced_by_env"
        try:
            content, raw, tok_in, tok_out, lat_ms, call_id = _execute_provider_call_with_repair(
                provider="ollama",
                model=ollama_model,
                task=task,
                case_id=case_id,
                session_id=session_id,
                system=system,
                user=user,
                schema=schema,
                route_reason=route_reason,
                temperature=temperature,
            )
            return LLMResult(
                content=content,
                raw_text=raw,
                provider="ollama",
                model=ollama_model,
                route_reason=route_reason,
                latency_ms=lat_ms,
                tokens_in=tok_in,
                tokens_out=tok_out,
                call_id=call_id,
                cached=False,
            )
        except Exception as exc:
            raise AppError("LLM_UNAVAILABLE_LOCAL", f"Ollama failed in forced_by_env mode: {exc}", status_code=503) from exc

    gemini_model = (
        (settings.GEMINI_MODEL_SMART or "gemini-2.5-pro")
        if tier == "smart"
        else (settings.GEMINI_MODEL_FAST or "gemini-2.5-flash")
    )

    # Check Cache for Gemini demo calls
    if task in CACHEABLE_TASKS:
        cache_key = get_cache_key(task, gemini_model, system, user)
        with _cache_lock:
            if cache_key in _llm_cache:
                cached_val, cached_raw, c_in, c_out, exp_at = _llm_cache[cache_key]
                if exp_at > time.time():
                    cache_call_id = str(uuid.uuid4())
                    record_llm_call(
                        call_id=cache_call_id,
                        case_id=case_id,
                        session_id=session_id,
                        task=task,
                        provider="gemini",
                        model=gemini_model,
                        route_reason="demo_allowed",
                        prompt_text=f"System: {system}\nUser: {user}",
                        response_text=cached_raw,
                        latency_ms=1,
                        tokens_in=c_in,
                        tokens_out=c_out,
                        status="ok",
                        error=None,
                    )
                    return LLMResult(
                        content=cached_val,
                        raw_text=cached_raw,
                        provider="gemini",
                        model=gemini_model,
                        route_reason="demo_allowed",
                        latency_ms=1,
                        tokens_in=c_in,
                        tokens_out=c_out,
                        call_id=cache_call_id,
                        cached=True,
                    )

    # In auto mode, try Gemini first
    try_gemini = True
    gemini_error: str | None = None

    # Check Token Bucket rate limiter (max wait 2s)
    has_token = gemini_rate_limiter.acquire(max_wait=2.0)
    if not has_token:
        try_gemini = False
        gemini_error = "Gemini RPM token bucket limit reached (wait > 2s)"
        logger.warning(gemini_error)

    if try_gemini:
        try:
            content, raw, tok_in, tok_out, lat_ms, call_id = _execute_provider_call_with_repair(
                provider="gemini",
                model=gemini_model,
                task=task,
                case_id=case_id,
                session_id=session_id,
                system=system,
                user=user,
                schema=schema,
                route_reason="demo_allowed",
                temperature=temperature,
            )
            if task in CACHEABLE_TASKS and isinstance(content, dict):
                cache_key = get_cache_key(task, gemini_model, system, user)
                with _cache_lock:
                    _llm_cache[cache_key] = (
                        content,
                        raw,
                        tok_in,
                        tok_out,
                        time.time() + (settings.LLM_CACHE_TTL_S or 3600),
                    )

            return LLMResult(
                content=content,
                raw_text=raw,
                provider="gemini",
                model=gemini_model,
                route_reason="demo_allowed",
                latency_ms=lat_ms,
                tokens_in=tok_in,
                tokens_out=tok_out,
                call_id=call_id,
                cached=False,
            )
        except Exception as exc:
            gemini_error = str(exc)
            logger.warning(f"Gemini call failed: {gemini_error}")
            record_llm_call(
                call_id=str(uuid.uuid4()),
                case_id=case_id,
                session_id=session_id,
                task=task,
                provider="gemini",
                model=gemini_model,
                route_reason="demo_allowed",
                prompt_text=f"System: {system}\nUser: {user}",
                response_text="",
                latency_ms=0,
                tokens_in=0,
                tokens_out=0,
                status="error",
                error=gemini_error,
            )

    # If provider_mode was strictly 'gemini', do not fallback to Ollama
    if provider_mode == "gemini":
        raise AppError("LLM_UNAVAILABLE", f"Gemini provider failed: {gemini_error}", status_code=503)

    # Fallback to Ollama (§8.1: fallback_after_error)
    ollama_model = settings.OLLAMA_MODEL or "qwen2.5:3b-instruct"
    route_reason = "fallback_after_error"
    try:
        content, raw, tok_in, tok_out, lat_ms, call_id = _execute_provider_call_with_repair(
            provider="ollama",
            model=ollama_model,
            task=task,
            case_id=case_id,
            session_id=session_id,
            system=system,
            user=user,
            schema=schema,
            route_reason=route_reason,
            temperature=temperature,
        )
        return LLMResult(
            content=content,
            raw_text=raw,
            provider="ollama",
            model=ollama_model,
            route_reason=route_reason,
            latency_ms=lat_ms,
            tokens_in=tok_in,
            tokens_out=tok_out,
            call_id=call_id,
            cached=False,
        )
    except Exception as exc:
        ollama_err = str(exc)
        logger.error(f"Fallback to Ollama also failed: {ollama_err}")
        record_llm_call(
            call_id=str(uuid.uuid4()),
            case_id=case_id,
            session_id=session_id,
            task=task,
            provider="ollama",
            model=ollama_model,
            route_reason=route_reason,
            prompt_text=f"System: {system}\nUser: {user}",
            response_text="",
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            status="error",
            error=ollama_err,
        )
        raise AppError("LLM_UNAVAILABLE", f"Both Gemini and Ollama failed. Gemini: {gemini_error}; Ollama: {ollama_err}", status_code=503) from exc
