from __future__ import annotations

import re
from typing import Any

_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "authorization",
    "cookie",
)

_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def _secret_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SECRET_KEY_PARTS)


def _secret_string(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)


def sanitize_metadata(value: Any) -> Any:
    """Best-effort defense against accidentally persisting obvious secrets.

    This is a guardrail, not a secret-management system. Operators and agents
    must still keep credentials out of Company Layer metadata entirely.
    """
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _secret_key(str(key)) else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, str) and _secret_string(value):
        return "[REDACTED]"
    return value
