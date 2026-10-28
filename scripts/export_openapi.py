#!/usr/bin/env python3
"""
OpenAPI Schema Exporter (§12 Step B12).

Exports the current OpenAPI 3.x schema from the VELORA FastAPI Hub
application into docs/openapi.json in valid, formatted JSON.
"""

import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import create_app  # noqa: E402


def export_openapi(output_path: Path | str = "docs/openapi.json") -> dict:
    app = create_app()
    openapi_schema = app.openapi()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, sort_keys=True)

    print(f"OpenAPI schema successfully exported to {out} with {len(openapi_schema.get('paths', {}))} paths.")
    return openapi_schema


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "docs/openapi.json"
    export_openapi(target)
