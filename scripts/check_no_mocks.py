#!/usr/bin/env python3
"""Fail if mock data, fake switches, secrets, or forbidden files are tracked. Exit 1 on any
finding."""
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".html", ".css", ".yml", ".yaml", ".toml", ".sh", ".sql", ".json"
}
SKIP_NAMES = {"pnpm-lock.yaml", "package-lock.json", "requirements.lock", "yarn.lock"}
SELF = {"scripts/check_no_mocks.py", "scripts/check_no_mocks.sh", ".githooks/pre-push"}
MAX_TEXT = 2_000_000
MAX_FILE = 5_000_000

MOCK_PATTERNS = [
    (r"\bUSE_MOCK\b|\bMOCK_(MODE|LLM|DATA|API|ML)\b|\bFAKE_(LLM|DATA|IMAGE|MODE)\b", "mock switch"),
    (r"lorem ipsum", "lorem ipsum"),
    (r"unittest\.mock|from mock import|\bjest\.mock|\bvi\.mock|\bmsw\b|\bfaker\b|\bFaker\(", "mocking library in app code"),
    (r"picsum\.photos|via\.placeholder\.com|placehold\.co|thispersondoesnotexist|randomuser\.me|pravatar|unsplash\.com", "stock/placeholder image"),
    (r"data:image/(png|jpe?g|webp);base64,[A-Za-z0-9+/=]{200,}", "embedded image blob"),
    (r"\b(sample|mock|fake|dummy|canned)_(response|llm|reply|output|face|image|attributes|statement)\b", "canned-data identifier"),
    (r"return\s*\{\s*[\"']mock[\"']", "mock return"),
]

SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"\bsk-[A-Za-z0-9]{20,}", "API secret key"),
    (r"\bhf_[A-Za-z0-9]{30,}", "Hugging Face token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.", "JWT"),
]
CRED_PATTERN = (r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']", "hard-coded credential")
E2E_PATTERN = (r"page\.route\(|route\.fulfill\(|\bsetupServer\(|\bmsw\b", "response interception in e2e")

SECRET_ENV_KEYS = ("GEMINI_API_KEY", "SERVICE_KEY", "JWT_SECRET", "HF_TOKEN", "CLOUDFLARE_API_TOKEN", "SEED_PASSWORD_")
BAD_EXT = {
    ".db", ".sqlite", ".sqlite3", ".safetensors", ".ckpt", ".pt", ".pth",
    ".onnx", ".joblib", ".bin", ".npy", ".npz", ".zip", ".gguf"
}
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3", ".webm", ".ogg", ".m4a", ".mp4"}
MEDIA_OK = ("frontend/public/", "frontend/src/assets/icons/", "docs/")  # + any /fixtures/ dir
FONT_OK = "backend/app/services/pdf/fonts/"


def tracked() -> list[str]:
    cmd = ["git", "ls-files"]
    if "--all" in sys.argv or "-a" in sys.argv or len(sys.argv) <= 1:
        cmd.extend(["-c", "-o", "--exclude-standard"])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if (ROOT / p).is_file()]


def is_test(p: str) -> bool:
    parts = p.replace("\\", "/").split("/")
    return "tests" in parts or "fixtures" in parts or "__tests__" in parts or p.endswith((".test.ts", ".test.tsx", ".spec.ts"))


def main() -> int:
    findings: list[str] = []
    for p in tracked():
        normalized_p = p.replace("\\", "/")
        if normalized_p in SELF or pathlib.PurePosixPath(normalized_p).name in SKIP_NAMES:
            continue
        path = ROOT / p
        ext = path.suffix.lower()
        size = path.stat().st_size
        name = path.name

        if name == ".env" or (name.startswith(".env") and name != ".env.example"):
            findings.append(f"{normalized_p}: env file tracked")
        if ext in BAD_EXT:
            findings.append(f"{normalized_p}: forbidden file type {ext}")
        if size > MAX_FILE and not normalized_p.startswith(FONT_OK):
            findings.append(f"{normalized_p}: file larger than 5 MB")
        if ext in MEDIA_EXT and not (normalized_p.startswith(MEDIA_OK) or "/fixtures/" in normalized_p):
            findings.append(f"{normalized_p}: media file outside allowed folders")
        if ext in {".ttf", ".otf"} and not normalized_p.startswith(FONT_OK):
            findings.append(f"{normalized_p}: font outside {FONT_OK}")

        if size > MAX_TEXT or (ext not in CODE_EXT and ext not in {".md", ".txt", ".env", ".example", ""} and name != ".env.example"):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "nomock-ok" in line:
                print(f"WARN {normalized_p}:{lineno}: nomock-ok marker (reviewed at G5)")
                continue
            for pat, why in SECRET_PATTERNS:
                if re.search(pat, line):
                    findings.append(f"{normalized_p}:{lineno}: {why}")
            if not is_test(normalized_p) and name != ".env.example" and ext in CODE_EXT:
                for pat, why in MOCK_PATTERNS:
                    if re.search(pat, line, re.IGNORECASE):
                        findings.append(f"{normalized_p}:{lineno}: {why}")
                if re.search(CRED_PATTERN[0], line):
                    findings.append(f"{normalized_p}:{lineno}: {CRED_PATTERN[1]}")
            if "tests/e2e/" in normalized_p or normalized_p.startswith("frontend/e2e/"):
                if re.search(E2E_PATTERN[0], line):
                    findings.append(f"{normalized_p}:{lineno}: {E2E_PATTERN[1]}")

    envx = ROOT / ".env.example"
    if envx.exists():
        for lineno, line in enumerate(envx.read_text(encoding="utf-8").splitlines(), 1):
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, rest = line.partition("=")
                value = rest.split("#", 1)[0].strip()
                if key.startswith(SECRET_ENV_KEYS) and value:
                    findings.append(f".env.example:{lineno}: secret variable {key} must be empty")

    if findings:
        print("\n".join(sorted(set(findings))))
        print(f"\n{len(set(findings))} finding(s).")
        return 1

    print("check_no_mocks: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
