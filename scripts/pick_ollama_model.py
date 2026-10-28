import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import settings  # noqa: E402
from backend.app.llm.providers.ollama import get_ollama_client  # noqa: E402


def main():
    print("=" * 60)
    print("VELORA: Ollama Model Selection & Benchmark")
    print("=" * 60)

    url = settings.OLLAMA_URL or "http://localhost:11434"
    print(f"Connecting to Ollama host: {url}")

    client = get_ollama_client(timeout_s=3.0)
    try:
        models_resp = client.list()
        models = getattr(models_resp, "models", []) or []
        model_names = [getattr(m, "model", str(m)) for m in models]
        print(f"Found {len(model_names)} models in local Ollama:")
        for name in model_names:
            print(f"  - {name}")
    except Exception as exc:
        print(f"\n[!] Ollama daemon is not responding on {url}.")
        print(f"    Error: {exc}")
        print("\nTo start Ollama and pull recommended models:")
        print("  1. Ensure Ollama service is running: `ollama serve`")
        print("  2. Pull a recommended model: `ollama pull qwen2.5:3b-instruct` or `ollama pull llama3.2:3b`")
        print("  3. Set OLLAMA_MODEL in .env: `OLLAMA_MODEL=qwen2.5:3b-instruct`")
        sys.exit(0)

    if not model_names:
        print("\nNo models found in local Ollama repository.")
        print("Recommended model to pull: `ollama pull qwen2.5:3b-instruct`")
        sys.exit(0)

    # Inspect probe set
    probe_path = ROOT_DIR / "backend" / "tests" / "fixtures" / "llm_probe_set.jsonl"
    probe_items = []
    if probe_path.exists():
        with open(probe_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    probe_items.append(json.loads(line))
        print(f"\nLoaded {len(probe_items)} probe items from {probe_path.name}")

    current_choice = settings.OLLAMA_MODEL
    print(f"\nCurrently configured OLLAMA_MODEL: {current_choice or 'None'}")
    if current_choice and current_choice in model_names:
        print(f"Active model '{current_choice}' is available locally.")
    else:
        # Suggest best default
        preferred_candidates = ["qwen2.5:3b-instruct", "llama3.2:3b", "gemma2:2b", "qwen2.5:1.5b"]
        chosen = None
        for candidate in preferred_candidates:
            if candidate in model_names:
                chosen = candidate
                break
        if not chosen and model_names:
            chosen = model_names[0]

        if chosen:
            print(f"\nRecommended model to set in .env: OLLAMA_MODEL={chosen}")

    print("\nBenchmark completed.")


if __name__ == "__main__":
    main()
