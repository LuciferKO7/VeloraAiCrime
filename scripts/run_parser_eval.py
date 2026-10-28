#!/usr/bin/env python3
"""
Evaluate attribute parser against llm_probe_set.jsonl (§8.1, §12 Step B10).
Supports:
  - Offline/deterministic evaluation using rule-based/fixture mock parsing
  - Live evaluation using local Ollama (`--live`)
"""
import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.services.eval_service import evaluate_probe_set  # noqa: E402


def simple_rule_parser(statement: str, language: str) -> dict:
    """
    Offline keyword-based fallback parser for testing/eval without requiring live GPU.
    """
    text_lower = statement.lower()
    attrs = {}

    if "young adult" in text_lower or "25 வயது" in text_lower or "20-25" in text_lower:
        attrs["age_band"] = "young_adult"
    elif "middle-aged" in text_lower or "middle aged" in text_lower:
        attrs["age_band"] = "middle_aged"
    elif "adult" in text_lower:
        attrs["age_band"] = "adult"
    elif "senior" in text_lower or "60" in text_lower:
        attrs["age_band"] = "senior"

    if "female" in text_lower or "woman" in text_lower or "பெண்" in text_lower:
        attrs["sex_presentation"] = "female"
    elif "male" in text_lower or "man" in text_lower or "ஆண்" in text_lower or "இளைஞன்" in text_lower:
        attrs["sex_presentation"] = "male"

    if "oval" in text_lower:
        attrs["face_shape"] = "oval"
    elif "round" in text_lower or "வட்ட முகம்" in text_lower:
        attrs["face_shape"] = "round"
    elif "square" in text_lower:
        attrs["face_shape"] = "square"

    if "black" in text_lower or "கருப்பு" in text_lower:
        attrs["hair_color"] = "black"
    elif "brown" in text_lower:
        attrs["hair_color"] = "brown"
    elif "grey" in text_lower:
        attrs["hair_color"] = "grey"

    if "short" in text_lower:
        attrs["hair_length"] = "short"
    elif "long" in text_lower:
        attrs["hair_length"] = "long"
    elif "bald" in text_lower:
        attrs["hair_length"] = "bald"

    if "mustache" in text_lower or "மீசை" in text_lower:
        attrs["facial_hair_type"] = "mustache"
    elif "beard" in text_lower:
        attrs["facial_hair_type"] = "beard"

    return attrs


def main():
    parser = argparse.ArgumentParser(description="Evaluate attribute parser on probe set")
    parser.add_argument(
        "--probe-set",
        type=str,
        default=str(ROOT_DIR / "backend" / "tests" / "fixtures" / "llm_probe_set.jsonl"),
        help="Path to probe set jsonl",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run genuine local Ollama evaluation (requires running Ollama)",
    )
    args = parser.parse_args()

    probe_path = Path(args.probe_set)
    if not probe_path.exists():
        print(f"Error: Probe set not found at {probe_path}", file=sys.stderr)
        sys.exit(1)

    if args.live:
        print(f"Running LIVE parser evaluation with local Ollama on {probe_path.name}...")
        from backend.app.llm.router import complete
        from backend.app.llm.schemas import get_statement_schema

        schema = get_statement_schema()

        def live_parser(statement: str, language: str) -> dict:
            try:
                res = complete(
                    task="parse",
                    case_id=None,
                    system="Extract facial attributes from statement.",
                    user=statement,
                    schema=schema,
                )
                if isinstance(res.content, dict):
                    return res.content.get("attributes", {})
                return {}
            except Exception as e:
                print(f"FATAL: Live Ollama parser evaluation failed: {e}", file=sys.stderr)
                sys.exit(1)

        parser_fn = live_parser
    else:
        print(f"Running deterministic offline evaluation on {probe_path.name}...")
        parser_fn = simple_rule_parser

    results = evaluate_probe_set(probe_path, parser_fn)
    print("\n" + "=" * 60)
    print("PARSER EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total Samples Evaluated: {results['total_samples']}")
    overall = results["overall"]
    print(f"Overall Precision: {overall['precision']:.4f}")
    print(f"Overall Recall:    {overall['recall']:.4f}")
    print(f"Overall F1 Score:  {overall['f1']:.4f}")
    print(f"True Positives:    {overall['tp']}")
    print(f"False Positives:   {overall['fp']}")
    print(f"False Negatives:   {overall['fn']}")

    print("\nBy Language:")
    for lang, m in results["by_language"].items():
        print(f"  [{lang}] P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} (TP={m['tp']} FP={m['fp']} FN={m['fn']})")

    print("\nBy Attribute:")
    for attr, m in results["by_attribute"].items():
        print(f"  {attr:<20}: P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f}")

    print("=" * 60)
    print("Full JSON:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

