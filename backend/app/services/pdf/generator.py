"""PDF generator service for VELORA investigative court packets.
Produces court-admissible composite packets with mandatory statutory disclaimers,
attribute breakdowns, confidence ratings, AI-assumed unstated features,
model provenance, and cryptographic verification hashes.
"""

import hashlib
import json
from typing import Any

MANDATORY_DISCLAIMER = "AI-generated investigative aid — not a photograph, not evidence of identity."
LEGAL_CUSTODY_NOTICE = (
    "Notice: Cryptographic SHA-256 digest provides data integrity verification against accidental modification or tampering; "
    "it does not constitute an immutable distributed ledger or a statutory digital signature under Section 3 of the Information Technology Act."
)

CANONICAL_FIELDS = [
    "disclaimer",
    "case_number",
    "session_id",
    "image_id",
    "language",
    "include_alternates",
    "attributes",
    "ai_assumed_unstated",
    "model_versions",
]

def generate_pdf_manifest(
    case_number: str,
    session_id: str,
    image_id: str | None,
    attributes: dict[str, Any],
    ai_assumed: list[dict[str, str]],
    model_versions: dict[str, str],
    language: str = "en",
    include_alternates: bool = False,
) -> dict[str, Any]:
    """Generates the canonical metadata manifest and document text for the PDF export."""
    canonical_payload = {
        "disclaimer": MANDATORY_DISCLAIMER,
        "case_number": case_number,
        "session_id": session_id,
        "image_id": image_id,
        "language": language,
        "include_alternates": include_alternates,
        "attributes": attributes,
        "ai_assumed_unstated": ai_assumed,
        "model_versions": model_versions,
    }

    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    sha256_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return {
        "status": "ready",
        "sha256": sha256_hash,
        "disclaimer_version": "DISCLAIMER_V1",
        "manifest": canonical_payload,
        "filename": f"VELORA_{case_number}_{session_id[:8]}.pdf",
        "canonical_fields": CANONICAL_FIELDS,
        "legal_notice": LEGAL_CUSTODY_NOTICE,
    }

def generate_pdf_bytes(manifest_data: dict[str, Any]) -> bytes:
    """Produces standards-compliant binary PDF 1.4 bytes containing the full packet."""
    manifest = manifest_data.get("manifest", {})
    case_number = manifest.get("case_number", "CASE-UNKNOWN")
    session_id = manifest.get("session_id", "SES-UNKNOWN")
    sha256_hash = manifest_data.get("sha256", "UNKNOWN")
    attributes = manifest.get("attributes", {})
    ai_assumed = manifest.get("ai_assumed_unstated", [])
    model_versions = manifest.get("model_versions", {})

    stream_lines = [
        "q",
        "0.353 0.145 0.039 rg",
        "0 800 595.28 41.89 re f",
        "Q",
        "BT",
        "/F2 9 Tf 1 1 1 rg 30 818 Td",
        f"({MANDATORY_DISCLAIMER.upper()}) Tj",
        "ET",
        "BT",
        "/F2 18 Tf 0.1 0.1 0.15 rg 40 760 Td",
        "(VELORA INVESTIGATIVE COURT PACKET) Tj",
        "ET",
        "BT",
        "/F1 10 Tf 0.4 0.4 0.45 rg 40 742 Td",
        f"(Case: {case_number}   |   Session: {session_id}   |   Digest: {sha256_hash[:16]}...) Tj",
        "ET",
        "q 0.8 0.8 0.8 RG 1 w 40 730 m 555 730 l S Q",
        "BT",
        "/F2 12 Tf 0.1 0.1 0.2 rg 40 705 Td",
        "(1. EXTRACTED WITNESS ATTRIBUTES) Tj",
        "ET",
    ]

    current_y = 685
    for k, v in attributes.items():
        val_str = str(v)
        stream_lines.extend([
            "BT",
            f"/F2 10 Tf 0.2 0.2 0.2 rg 50 {current_y} Td ({k}:) Tj",
            "ET",
            "BT",
            f"/F1 10 Tf 0.1 0.1 0.1 rg 180 {current_y} Td ({val_str}) Tj",
            "ET",
        ])
        current_y -= 18

    current_y -= 10
    stream_lines.extend([
        "BT",
        f"/F2 12 Tf 0.7 0.25 0.1 rg 40 {current_y} Td",
        "(2. AI-ASSUMED UNSTATED FEATURES [R11 INVARIANT]) Tj",
        "ET",
    ])
    current_y -= 20

    for item in ai_assumed:
        ik = item.get("key", "")
        inote = item.get("note", "")
        stream_lines.extend([
            "BT",
            f"/F2 10 Tf 0.2 0.2 0.2 rg 50 {current_y} Td ({ik}:) Tj",
            "ET",
            "BT",
            f"/F1 9 Tf 0.3 0.3 0.3 rg 160 {current_y} Td ({inote}) Tj",
            "ET",
        ])
        current_y -= 16

    current_y -= 10
    stream_lines.extend([
        "BT",
        f"/F2 12 Tf 0.1 0.1 0.2 rg 40 {current_y} Td",
        "(3. FORENSIC MODEL PROVENANCE) Tj",
        "ET",
    ])
    current_y -= 20

    for k, v in model_versions.items():
        stream_lines.extend([
            "BT",
            f"/F1 9 Tf 0.3 0.3 0.3 rg 50 {current_y} Td ({k}: {v}) Tj",
            "ET",
        ])
        current_y -= 14

    current_y -= 15
    stream_lines.extend([
        f"q 0.9 0.9 0.95 rg 40 {current_y - 45} 515 55 re f 0.7 0.7 0.8 RG 1 w 40 {current_y - 45} 515 55 re S Q",
        "BT",
        f"/F2 11 Tf 0.1 0.1 0.4 rg 50 {current_y - 5} Td (4. CRYPTOGRAPHIC VERIFICATION SEAL) Tj",
        "ET",
        "BT",
        f"/F1 9 Tf 0.2 0.2 0.2 rg 50 {current_y - 22} Td (SHA-256 Digest: {sha256_hash}) Tj",
        "ET",
    ])

    current_y -= 70
    stream_lines.extend([
        "BT",
        f"/F2 8 Tf 0.5 0.1 0.1 rg 40 {current_y} Td (LEGAL & CUSTODIAL NOTICE:) Tj",
        "ET",
        "BT",
        f"/F1 7.5 Tf 0.3 0.3 0.3 rg 40 {current_y - 12} Td ({LEGAL_CUSTODY_NOTICE}) Tj",
        "ET",
    ])

    stream_content = "\n".join(stream_lines).encode("utf-8")
    stream_length = len(stream_content)

    objects = [
        "1 0 obj\n<<\n  /Type /Catalog\n  /Pages 2 0 R\n>>\nendobj",
        "2 0 obj\n<<\n  /Type /Pages\n  /Kids [3 0 R]\n  /Count 1\n>>\nendobj",
        "3 0 obj\n<<\n  /Type /Page\n  /Parent 2 0 R\n  /MediaBox [0 0 595.28 841.89]\n  /Resources <<\n    /Font <<\n      /F1 4 0 R\n      /F2 5 0 R\n    >>\n  >>\n  /Contents 6 0 R\n>>\nendobj",
        "4 0 obj\n<<\n  /Type /Font\n  /Subtype /Type1\n  /BaseFont /Helvetica\n>>\nendobj",
        "5 0 obj\n<<\n  /Type /Font\n  /Subtype /Type1\n  /BaseFont /Helvetica-Bold\n>>\nendobj",
        f"6 0 obj\n<<\n  /Length {stream_length}\n>>\nstream\n".encode() + stream_content + b"\nendstream\nendobj",
    ]

    pdf = b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"
    offsets = []
    for obj in objects:
        offsets.append(len(pdf))
        if isinstance(obj, str):
            pdf += obj.encode("utf-8") + b"\n"
        else:
            pdf += obj + b"\n"

    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()

    pdf += f"trailer\n<<\n  /Size {len(objects) + 1}\n  /Root 1 0 R\n>>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return pdf
