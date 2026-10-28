import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def load_probe_set(probe_set_path: Path | str) -> list[dict[str, Any]]:
    """
    Loads and validates the probe set JSONL file (§8.1, §12 Step B10).
    Raises FileNotFoundError if file is missing.
    Raises ValueError if any line is malformed or missing required schema fields.
    """
    path = Path(probe_set_path)
    if not path.is_file():
        raise FileNotFoundError(f"Probe set file not found: {path.resolve()}")

    items = []
    with open(path, encoding="utf-8") as f:
        for idx, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception as exc:
                raise ValueError(f"Malformed JSON on line {idx}: {exc}") from exc

            if not isinstance(record, dict):
                raise ValueError(f"Expected JSON object on line {idx}")

            for required_field in ("id", "language", "statement", "expected_attributes"):
                if required_field not in record:
                    raise ValueError(f"Missing required field '{required_field}' on line {idx}")

            if not isinstance(record["expected_attributes"], dict):
                raise ValueError(f"Field 'expected_attributes' must be a dict on line {idx}")

            items.append(record)

    if not items:
        raise ValueError(f"Probe set file is empty: {path.resolve()}")

    return items


def compute_attribute_metrics(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """
    Computes precision, recall, and F1 deterministically for extracted facial attributes.
    Matches exact (attribute, value) pairs.
    """
    if len(predictions) != len(ground_truths):
        raise ValueError("Predictions and ground truths list lengths must match")

    total_tp = 0
    total_fp = 0
    total_fn = 0

    lang_stats: dict[str, dict[str, int]] = {}
    attr_stats: dict[str, dict[str, int]] = {}

    for idx, (pred, gt) in enumerate(zip(predictions, ground_truths, strict=True)):
        lang = languages[idx] if languages and idx < len(languages) else "unknown"
        if lang not in lang_stats:
            lang_stats[lang] = {"tp": 0, "fp": 0, "fn": 0}

        # Compare predicted against ground truth
        for k, v in pred.items():
            if k not in attr_stats:
                attr_stats[k] = {"tp": 0, "fp": 0, "fn": 0}

            if k in gt and gt[k] == v:
                total_tp += 1
                lang_stats[lang]["tp"] += 1
                attr_stats[k]["tp"] += 1
            else:
                total_fp += 1
                lang_stats[lang]["fp"] += 1
                attr_stats[k]["fp"] += 1

        # Compare ground truth for misses (FN)
        for k, v in gt.items():
            if k not in attr_stats:
                attr_stats[k] = {"tp": 0, "fp": 0, "fn": 0}

            if k not in pred or pred[k] != v:
                total_fn += 1
                lang_stats[lang]["fn"] += 1
                attr_stats[k]["fn"] += 1

    def calc_prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        return {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    by_language = {lang: calc_prf(s["tp"], s["fp"], s["fn"]) for lang, s in sorted(lang_stats.items())}
    by_attribute = {attr: calc_prf(s["tp"], s["fp"], s["fn"]) for attr, s in sorted(attr_stats.items())}

    overall = calc_prf(total_tp, total_fp, total_fn)

    return {
        "total_samples": len(predictions),
        "overall": overall,
        "by_language": by_language,
        "by_attribute": by_attribute,
    }


def evaluate_probe_set(
    probe_set_path: Path | str,
    parser_fn: Callable[[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """
    Evaluates a parser function against the probe set file.
    Does not make external network calls or require live LLMs.
    """
    records = load_probe_set(probe_set_path)

    predictions = []
    ground_truths = []
    languages = []

    for item in records:
        statement = item["statement"]
        lang = item["language"]
        pred = parser_fn(statement, lang) or {}
        # Normalize prediction if wrapped in attributes dictionary
        if "attributes" in pred and isinstance(pred["attributes"], dict):
            flat_pred = {}
            for k, val in pred["attributes"].items():
                if isinstance(val, dict) and "value" in val:
                    flat_pred[k] = val["value"]
                else:
                    flat_pred[k] = val
            pred = flat_pred

        predictions.append(pred)
        ground_truths.append(item["expected_attributes"])
        languages.append(lang)

    metrics = compute_attribute_metrics(predictions, ground_truths, languages=languages)
    metrics["probe_set_path"] = str(Path(probe_set_path).name)
    return metrics

