"""BrainSafetyGuard — keeps the Super Brain safe by default.

V1 is read-only reasoning: the guard never lets a secret value leave the system
and treats all brain output as advice (no action is ever executed). It redacts
secret-looking values from any text or nested structure before it is persisted
or returned.
"""

from __future__ import annotations

import re

# key: value style secrets (api_key=..., authorization: Bearer xyz, password=...)
_KV_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization|bearer|client[_-]?secret|access[_-]?key)\b"
    r"\s*[:=]\s*\S+"
)
# Long opaque tokens / high-entropy strings.
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
# Common provider key prefixes.
_PREFIXED = re.compile(r"\b(?:sk-|ghp_|gho_|github_pat_|xox[baprs]-|AKIA)[A-Za-z0-9_\-]+\b")

REDACTED = "***redacted***"


class BrainSafetyGuard:
    read_only = True

    def redact(self, text: str | None) -> str | None:
        if not text:
            return text
        out = _PREFIXED.sub(REDACTED, text)
        out = _KV_SECRET.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
        out = _LONG_TOKEN.sub(REDACTED, out)
        return out

    def sanitize(self, value):
        """Recursively redact strings inside dicts/lists/tuples."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {k: self.sanitize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.sanitize(v) for v in value]
        return value
