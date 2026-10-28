import time
from typing import Any

import ollama

from backend.app.core.config import settings


def get_ollama_client(timeout_s: float | None = None) -> ollama.Client:
    host = settings.OLLAMA_URL or "http://localhost:11434"
    if timeout_s is None:
        timeout_s = float(settings.LLM_TIMEOUT_S)
    return ollama.Client(host=host, timeout=timeout_s)


def call_ollama(
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any] | None = None,
    temperature: float = 0.0,
    timeout_s: float | None = None,
) -> tuple[str, int, int, int]:
    """
    Calls local Ollama instance via official ollama Python client.
    Returns: (response_text, tokens_in, tokens_out, latency_ms)
    """
    client = get_ollama_client(timeout_s=timeout_s)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    options: dict[str, Any] = {
        "temperature": temperature,
    }

    clean_schema: Any = None
    if schema:
        clean_schema = dict(schema)
        clean_schema.pop("$schema", None)

    start_time = time.perf_counter()
    response = client.chat(
        model=model,
        messages=messages,
        format=clean_schema,
        options=options,
        keep_alive="30m",
    )
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    raw_text = ""
    if hasattr(response, "message") and response.message:
        raw_text = getattr(response.message, "content", "") or ""
    elif isinstance(response, dict):
        raw_text = response.get("message", {}).get("content", "")

    tokens_in = getattr(response, "prompt_eval_count", 0) or 0
    tokens_out = getattr(response, "eval_count", 0) or 0

    return raw_text, tokens_in, tokens_out, elapsed_ms
