import time
from typing import Any

from google import genai
from google.genai import types

from backend.app.core.config import settings


def get_gemini_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=api_key)


def call_gemini(
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any] | None = None,
    temperature: float = 0.0,
    timeout_s: float | None = None,
) -> tuple[str, int, int, int]:
    """
    Calls Google Gemini using the official google-genai SDK.
    Returns: (response_text, tokens_in, tokens_out, latency_ms)
    """
    client = get_gemini_client()

    config_args: dict[str, Any] = {
        "temperature": temperature,
    }
    if system:
        config_args["system_instruction"] = system

    if schema:
        config_args["response_mime_type"] = "application/json"
        # Sanitize schema for GenAI API (remove $schema, definitions if top level)
        clean_schema = dict(schema)
        clean_schema.pop("$schema", None)
        config_args["response_schema"] = clean_schema

    if timeout_s is None:
        timeout_s = float(settings.LLM_TIMEOUT_S)

    http_options = types.HttpOptions(timeout=int(timeout_s * 1000))
    config_args["http_options"] = http_options

    config = types.GenerateContentConfig(**config_args)

    start_time = time.perf_counter()
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=config,
    )
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    tokens_in = 0
    tokens_out = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
        tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

    text = response.text or ""
    return text, tokens_in, tokens_out, elapsed_ms
