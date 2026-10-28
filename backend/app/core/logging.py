import logging
import re
import sys

_SENSITIVE_PATTERNS = [
    # Bearer tokens (precedes JWT regex so Bearer <token> is cleanly redacted as Bearer [REDACTED])
    (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~+/]+=*", re.IGNORECASE), "Bearer [REDACTED]"),
    # JWT tokens
    (re.compile(r"ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[JWT_REDACTED]"),
    # Passwords in JSON / query params / key-value
    (re.compile(r'(["\']?password["\']?\s*[:=]\s*["\'])(?:(?=(\\?))\2.)*?(["\'])', re.IGNORECASE), r"\1[REDACTED]\3"),
    # API keys / secrets
    (re.compile(r'(["\']?(?:api[_-]?key|secret|service[_-]?key)["\']?\s*[:=]\s*["\'])(?:(?=(\\?))\2.)*?(["\'])', re.IGNORECASE), r"\1[REDACTED]\3"),
    # Base64 image data URIs or long base64 strings
    (re.compile(r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]{30,}"), "data:image/...;base64,[REDACTED]"),
    (re.compile(r"[A-Za-z0-9+/]{100,}={0,2}"), "[BASE64_BLOB_REDACTED]"),
]


def sanitize_log_message(msg: str) -> str:
    """Sanitize sensitive patterns from a string message."""
    if not isinstance(msg, str):
        return msg
    for pattern, repl in _SENSITIVE_PATTERNS:
        msg = pattern.sub(repl, msg)
    return msg


class SensitiveDataFilter(logging.Filter):
    """
    Filter that scrubs witness text, passwords, JWTs, API keys, and base64 payloads
    from log records (§12 Step B12).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_log_message(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (sanitize_log_message(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    sanitize_log_message(v) if isinstance(v, str) else v
                    for v in record.args
                )
        return True


def setup_logging():
    logger = logging.getLogger("velora")
    logger.setLevel(logging.INFO)

    sensitive_filter = SensitiveDataFilter()
    logger.addFilter(sensitive_filter)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.addFilter(sensitive_filter)
        formatter = logging.Formatter(
            fmt='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()
