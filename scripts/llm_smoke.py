import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import settings  # noqa: E402
from backend.app.llm.providers.gemini import call_gemini  # noqa: E402
from backend.app.llm.providers.ollama import call_ollama  # noqa: E402
from backend.app.llm.router import complete  # noqa: E402


def main():
    print("=" * 60)
    print("VELORA Step B3: LLM Layer Smoke Test")
    print("=" * 60)

    # 1. Inspect Environment Config (without exposing secrets)
    gemini_key_set = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())
    print(f"Gemini API Key: {'Configured (masked)' if gemini_key_set else 'NOT CONFIGURED'}")
    print(f"Gemini Fast Model: {settings.GEMINI_MODEL_FAST or 'default'}")
    print(f"Gemini Smart Model: {settings.GEMINI_MODEL_SMART or 'default'}")
    print(f"Ollama URL: {settings.OLLAMA_URL or 'http://localhost:11434'}")
    print(f"Ollama Model: {settings.OLLAMA_MODEL or 'default'}")
    print(f"Provider Mode: {settings.LLM_PROVIDER_MODE}")
    print("-" * 60)

    # Load Smoke Schema
    smoke_schema_path = ROOT_DIR / "backend" / "app" / "llm" / "schemas" / "smoke.json"
    with open(smoke_schema_path, encoding="utf-8") as f:
        smoke_schema = json.load(f)

    # 2. Test Gemini Direct (if configured)
    print("\n[1/3] Testing Gemini Provider:")
    if not gemini_key_set:
        print("  SKIPPED: GEMINI_API_KEY is not set in environment/.env")
    else:
        try:
            model = settings.GEMINI_MODEL_FAST or "gemini-2.5-flash"
            print(f"  Pinging Gemini model '{model}'...")
            _, _, _, lat_ms = call_gemini(
                model=model,
                system="You are a health check agent.",
                user="Return JSON with status 'ok' and provider 'gemini'.",
                schema=smoke_schema,
                temperature=0.0,
                timeout_s=5.0,
            )
            print(f"  SUCCESS: Gemini responded in {lat_ms} ms")
        except Exception as exc:
            print(f"  FAILED: Gemini error: {exc}")

    # 3. Test Ollama Direct
    print("\n[2/3] Testing Ollama Provider:")
    try:
        model = settings.OLLAMA_MODEL or "qwen2.5:3b-instruct"
        print(f"  Pinging Ollama on {settings.OLLAMA_URL} with model '{model}'...")
        _, _, _, lat_ms = call_ollama(
            model=model,
            system="You are a health check agent.",
            user="Return JSON with status 'ok' and provider 'ollama'.",
            schema=smoke_schema,
            temperature=0.0,
            timeout_s=5.0,
        )
        print(f"  SUCCESS: Ollama responded in {lat_ms} ms")
    except Exception as exc:
        print(f"  UNAVAILABLE: Ollama error: {exc}")

    # 4. Test Router End-to-End
    print("\n[3/3] Testing LLM Router (complete(task='smoke', case_id=None)):")
    try:
        result = complete(
            task="smoke",
            case_id=None,
            system="You are a smoke tester.",
            user="Generate smoke status ok.",
            schema=smoke_schema,
            tier="fast",
            temperature=0.0,
        )
        print("  Router result:")
        print(f"    Provider:     {result.provider}")
        print(f"    Model:        {result.model}")
        print(f"    Route Reason: {result.route_reason}")
        print(f"    Latency:      {result.latency_ms} ms")
        print(f"    Tokens In/Out:{result.tokens_in}/{result.tokens_out}")
        print(f"    Call ID:      {result.call_id}")
        print(f"    Content:      {result.content}")
        print("  SUCCESS: Router smoke test passed.")
    except Exception as exc:
        print(f"  ROUTER NOTICE: Router call completed with exception: {exc}")

    print("\n" + "=" * 60)
    print("LLM Smoke check finished.")
    print("=" * 60)


if __name__ == "__main__":
    main()
