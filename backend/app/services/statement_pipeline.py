import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.llm.guards import validate_and_guard_parse_delta
from backend.app.llm.router import complete
from backend.app.services.sessions import SALIENT_KEYS

logger = logging.getLogger("velora.statement_pipeline")

ROOT = Path(__file__).resolve().parent.parent.parent.parent
FACE_SCHEMA_PATH = ROOT / "contracts/face_attributes.schema.json"
PARSE_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm/prompts/parse_system.md"

INDIC_SCRIPT_RANGES = [
    (0x0B80, 0x0BFF, "ta"),  # Tamil
    (0x0C00, 0x0C7F, "te"),  # Telugu
    (0x0C80, 0x0CFF, "kn"),  # Kannada
    (0x0D00, 0x0D7F, "ml"),  # Malayalam
    (0x0980, 0x09FF, "bn"),  # Bengali
    (0x0900, 0x097F, "hi"),  # Devanagari (Hindi / Marathi)
]

SALIENT_QUESTIONS: dict[str, str] = {
    "face_shape": "Could you describe the general shape of their face (e.g., oval, round, square, or long)?",
    "hair_length": "How long was their hair?",
    "hair_style": "What was their hair style and appearance like?",
    "hair_color": "What color was their hair?",
    "facial_hair_type": "Did they have any facial hair, such as a mustache, beard, or stubble?",
    "eye_shape": "Do you recall the shape or size of their eyes?",
    "eye_color": "Do you remember the color of their eyes?",
    "nose_bridge": "Could you describe their nose bridge and tip?",
    "jaw_shape": "Did they have a square, pointed, or rounded jawline?",
    "chin": "Did they have a prominent, pointed, or rounded chin?",
    "skin_tone": "Do you recall any details about their complexion or skin tone?",
    "forehead": "Was their forehead prominent, average, or low?",
    "cheeks": "Did they have high cheekbones, full cheeks, or sunken cheeks?",
    "eyebrow_thickness": "Were their eyebrows thick, thin, or bushy?",
    "lips_fullness": "Were their lips thin, medium, or full?",
    "ears": "Did they have noticeably large, small, or protruding ears?",
    "glasses": "Were they wearing any glasses?",
    "headwear": "Were they wearing a cap, turban, helmet, or other headwear?",
}


def detect_language(text_str: str, preferred_hint: str | None = None) -> str:
    """
    Detects language based on Indic script Unicode code points, falling back to English.
    """
    if not text_str:
        return preferred_hint or "en"

    counts: dict[str, int] = {}
    for ch in text_str:
        cp = ord(ch)
        for start, end, lang in INDIC_SCRIPT_RANGES:
            if start <= cp <= end:
                if lang == "hi" and preferred_hint == "mr":
                    counts["mr"] = counts.get("mr", 0) + 1
                else:
                    counts[lang] = counts.get(lang, 0) + 1
                break

    if counts:
        best_lang = max(counts.items(), key=lambda kv: kv[1])[0]
        return best_lang

    # Check ASCII / Latin
    if preferred_hint in ("en", "ta", "hi", "te", "kn", "ml", "bn", "mr") and not re.search(r"[a-zA-Z]", text_str):
        return preferred_hint

    return "en"


def translate_text(
    original_text: str,
    src_lang: str,
    *,
    case_id: str | None = None,
    session_id: str | None = None,
) -> tuple[str, str]:
    """
    Translates text to English:
    - If src_lang == 'en', returns (original_text, 'none').
    - Tries speech service /sp/v1/translate with 5s timeout.
    - If unavailable, falls back to LLM router 'translate' task.
    """
    if src_lang == "en":
        return original_text, "none"

    try:
        from backend.app.services.speech_proxy import SpeechProxyClient
        client = SpeechProxyClient(timeout_s=5.0)
        res = client.translate(original_text, src_lang, target_lang="en")
        translated = res.get("translated_text")
        if translated:
            return translated.strip(), "indictrans2"
    except Exception as exc:
        logger.warning("Speech service translation unavailable, falling back to LLM router: %s", exc)

    # Fallback to LLM Router
    system_prompt = "You are a professional translator for investigative law enforcement. Translate the provided regional language text accurately into standard English. Return ONLY the English translation without preamble or commentary."
    llm_res = complete(
        "translate",
        case_id=case_id,
        session_id=session_id,
        system=system_prompt,
        user=original_text,
    )
    translated_text = llm_res.raw_text.strip()
    return translated_text, llm_res.provider


def parse_statement(
    english_text: str,
    current_attributes: dict[str, Any],
    *,
    conn: Connection,
    case_id: str | None = None,
    session_id: str | None = None,
    original_lang: str = "en",
) -> tuple[dict[str, Any], str | None]:
    """
    Parses English statement into facial attributes using LLM router, glossary, and safety guards.
    Returns (guarded_delta, llm_call_id).
    """
    # 1. Fetch approved glossary terms
    terms_rows = conn.execute(
        text(
            """
            SELECT term, maps_to_json
            FROM glossary_terms
            WHERE status = 'approved' AND (language = :lang OR language = 'en')
            """
        ),
        {"lang": original_lang},
    ).fetchall()
    glossary_mappings = {}
    for r in terms_rows:
        try:
            glossary_mappings[r[0]] = json.loads(r[1])
        except Exception:
            pass

    # 2. Load schema and prompt
    schema = {}
    if FACE_SCHEMA_PATH.exists():
        try:
            schema = json.loads(FACE_SCHEMA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    parse_system_prompt = "You convert a witness's description of a person's FACE into JSON matching the schema. Follow all Responsible AI rules strictly: NEVER infer appearance_group, skin_tone, religion, or caste."
    if PARSE_SYSTEM_PROMPT_PATH.exists():
        try:
            parse_system_prompt = PARSE_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        except Exception:
            pass

    user_payload = f"Statement: {english_text}\nCurrent attributes: {json.dumps(current_attributes.get('attributes', {}))}"
    if glossary_mappings:
        user_payload += f"\nApproved Glossary: {json.dumps(glossary_mappings)}"

    # 3. Call LLM Router
    llm_res = complete(
        "parse",
        case_id=case_id,
        session_id=session_id,
        system=parse_system_prompt,
        user=user_payload,
        schema=schema,
    )

    content = llm_res.content if isinstance(llm_res.content, dict) else {}
    if not content and llm_res.raw_text:
        try:
            content = json.loads(llm_res.raw_text)
        except Exception:
            content = {"attributes": {}}

    # 4. Apply Safety Guards (§8.2, TB3.8)
    guarded_delta, _dropped = validate_and_guard_parse_delta(
        content,
        english_text,
        extra_glossary_descriptors=list(glossary_mappings.keys()),
    )

    return guarded_delta, llm_res.call_id


def merge_attributes(
    current_snapshot: dict[str, Any],
    delta: dict[str, Any],
    *,
    source_override: str | None = None,
) -> dict[str, Any]:
    """
    Merges parsed or user-edited delta into current attributes snapshot.
    Preserves schema_version, updates attributes, appends new unmapped_notes.
    """
    merged = {
        "schema_version": current_snapshot.get("schema_version", "1.0"),
        "attributes": dict(current_snapshot.get("attributes") or {}),
        "unmapped_notes": list(current_snapshot.get("unmapped_notes") or []),
    }

    delta_attrs = delta.get("attributes") or {}
    for k, v in delta_attrs.items():
        if isinstance(v, dict):
            item = dict(v)
            if source_override:
                item["source"] = source_override
            merged["attributes"][k] = item

    for note in delta.get("unmapped_notes") or []:
        if note and note not in merged["unmapped_notes"]:
            merged["unmapped_notes"].append(note)

    return merged


def generate_next_question(
    current_attributes: dict[str, Any],
    *,
    case_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Derives next investigative question per §8.5 based on missing high-variance salient attributes.
    """
    attr_map = current_attributes.get("attributes") or {}
    for key in SALIENT_KEYS:
        val = attr_map.get(key)
        if not val or val.get("value") is None:
            if key in SALIENT_QUESTIONS:
                return SALIENT_QUESTIONS[key]

    return "Are there any specific distinctive marks, scars, tattoos, or clothing details you recall about the suspect?"


def suggest_glossary_terms_background(
    unmapped_notes: list[str],
    case_id: str,
    session_id: str,
    original_lang: str,
) -> None:
    """
    For demo cases, optionally suggests new glossary terms from unmapped notes in background.
    """
    if not unmapped_notes or original_lang == "en":
        return
    try:
        notes_str = ", ".join(unmapped_notes)
        complete(
            "glossary_suggest",
            case_id=case_id,
            session_id=session_id,
            system="Identify potential Indian regional facial descriptor terms from the provided notes and suggest schema mappings.",
            user=f"Language: {original_lang}\nNotes: {notes_str}",
        )
    except Exception as exc:
        logger.debug("Background glossary suggest skipped: %s", exc)
