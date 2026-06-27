"""Failure log parsing + classification for Debug Intelligence (Phase 12.3).

Pure, read-only text analysis: classify a failure log into a known type, extract
affected files, the salient error message, stack frames / failing tests, and a
normalized signature used to group recurring failures. No code is executed.
"""

from __future__ import annotations

import re

# type -> list of (lowercased substring, weight). Higher weight = more specific.
_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "migration_error": [("alembic", 3), ("duplicatecolumn", 3), ("duplicateobject", 3),
                        ("target database is not up to date", 3), ("can't locate revision", 3),
                        ("multiple head revisions", 3), ("op.create_table", 1), ("migration", 1)],
    "ai_provider_error": [("ratelimiterror", 3), ("rate limit", 2), ("invalid api key", 3),
                          ("insufficient_quota", 3), ("authenticationerror", 2), ("groq", 2),
                          ("openai", 2), ("anthropic", 2), ("provider_router", 3), ("model_not_found", 3)],
    "webhook_error": [("x-hub-signature", 3), ("signature verification", 3), ("invalid signature", 3),
                      ("webhook", 2), ("payload", 1), ("delivery", 1)],
    "celery_error": [("workerlosterror", 3), ("kombu", 3), ("billiard", 3), ("[celery", 2),
                     ("celery", 2), ("acks_late", 2), ("task ", 1), ("broker", 1)],
    "workspace_failure": [("did not become ready", 3), ("container exited", 3), ("exit 137", 3),
                          ("sandbox", 2), ("workspaceinstance", 3), ("readiness", 2), ("workspace", 2),
                          ("docker", 1)],
    "dependency_error": [("modulenotfounderror", 3), ("no module named", 3), ("importerror", 2),
                         ("cannot find module", 3), ("eresolve", 3), ("npm err!", 2),
                         ("could not find a version", 3), ("could not be resolved", 2)],
    "build_failure": [("failed to compile", 3), ("error ts", 3), ("type error", 2), ("npm run build", 2),
                      ("next build", 2), ("webpack", 2), ("tsc", 1), ("module not found", 2)],
    "lint_failure": [("eslint", 3), ("ruff", 3), ("flake8", 3), ("pylint", 2), ("prettier", 2),
                     ("no-unused-vars", 3), ("max-warnings", 3), ("e501", 2), ("f401", 2), ("lint", 1)],
    "test_failure": [("=== failures ===", 3), ("short test summary", 3), ("test session starts", 3),
                     ("assertionerror", 3), ("failed ", 1), ("pytest", 2), ("::test", 2), ("assert ", 1)],
    "configuration_error": [("keyerror", 2), ("environment variable", 3), ("missing env", 3),
                            ("pydantic", 2), ("validationerror", 2), (" is not set", 3), (".env", 1),
                            ("settings", 1)],
    "runtime_error": [("traceback (most recent call last)", 2), ("exception", 1), ("error:", 1), ("raise ", 1)],
}

# Tie-break order: more specific types win when scores are equal.
_PRIORITY = [
    "migration_error", "ai_provider_error", "webhook_error", "celery_error", "workspace_failure",
    "dependency_error", "build_failure", "lint_failure", "test_failure", "configuration_error", "runtime_error",
]

_FILE_RE = re.compile(
    r"(?:(?<=[\s\"'(:])|^)((?:[\w.\-]+/)*[\w.\-]+\.(?:py|tsx?|jsx?|go|rs|java|rb|php|sql|ya?ml|toml|cfg|ini|css|html|mjs|cjs))",
    re.MULTILINE,
)
_EXCLUDE_PATH = ("site-packages/", "node_modules/", "dist/", ".venv/", "build/", ".next/")
_FRAME_RE = re.compile(r'File "(.+?)", line (\d+), in (\S+)')
_PYTEST_FAILED_RE = re.compile(r"FAILED\s+(\S+::\S+)")
_PYTEST_NODE_RE = re.compile(r"((?:\w[\w./-]*)\.py)::(\w+)")
_ERROR_LINE_RE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning))\b:?\s*(.*)$")
_TS_ERROR_RE = re.compile(r"(?:error TS\d+|Type error)\s*:?\s*(.+)")


def classify(text: str, *, source_hint: str | None = None) -> str:
    low = (text or "").lower()
    scores: dict[str, int] = {}
    for ftype, signals in _SIGNALS.items():
        score = sum(weight for needle, weight in signals if needle in low)
        if score:
            scores[ftype] = score
    if source_hint:
        # A trusted source nudges (not forces) the classification.
        hint = source_hint.lower()
        for ftype in scores:
            if ftype.split("_")[0] in hint:
                scores[ftype] += 2
        if source_hint == "workspace":
            scores["workspace_failure"] = scores.get("workspace_failure", 0) + 3
    if not scores:
        return "runtime_error"
    best = max(scores.values())
    for ftype in _PRIORITY:
        if scores.get(ftype) == best:
            return ftype
    return "runtime_error"


def extract_files(text: str) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for m in _FILE_RE.finditer(text or ""):
        path = m.group(1)
        if any(seg in path for seg in _EXCLUDE_PATH):
            continue
        if path not in seen and "." in path:
            seen.add(path)
            files.append(path)
    return files[:20]


def _error_message(text: str, failure_type: str) -> str:
    lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    if failure_type == "build_failure":
        for ln in lines:
            m = _TS_ERROR_RE.search(ln)
            if m:
                return m.group(1).strip()[:300]
        for ln in lines:
            if "module not found" in ln.lower():
                return ln.strip()[:300]
    # pytest assertion / E-lines
    e_lines = [ln for ln in lines if ln.lstrip().startswith("E ")]
    if e_lines:
        return e_lines[-1].lstrip("E").strip()[:300]
    # Last "<SomeError>: message" line.
    for ln in reversed(lines):
        m = _ERROR_LINE_RE.match(ln.strip())
        if m:
            return f"{m.group(1)}: {m.group(2)}".strip()[:300]
    return lines[-1][:300]


def _normalize(message: str) -> str:
    norm = re.sub(r"0x[0-9a-fA-F]+", "<hex>", message)
    norm = re.sub(r"\d+", "#", norm)
    norm = re.sub(r"['\"]", "", norm)
    return norm.lower().strip()[:160]


def parse(text: str, failure_type: str) -> dict:
    files = extract_files(text)
    frames = [
        {"file": f, "line": int(ln), "func": fn}
        for f, ln, fn in _FRAME_RE.findall(text or "")
        if not any(seg in f for seg in _EXCLUDE_PATH)
    ]
    failing = list(dict.fromkeys(_PYTEST_FAILED_RE.findall(text or "")))
    if not failing:
        failing = [f"{p}::{t}" for p, t in _PYTEST_NODE_RE.findall(text or "")][:10]
    error_message = _error_message(text, failure_type)

    # The most relevant file: prefer the deepest project stack frame.
    project_frames = [fr["file"] for fr in frames]
    primary_file = project_frames[-1] if project_frames else (files[0] if files else None)
    if primary_file and primary_file not in files:
        files.insert(0, primary_file)

    title = error_message or (failing[0] if failing else f"{failure_type.replace('_', ' ').title()}")
    signature = f"{failure_type}:{_normalize(error_message)}"
    if primary_file:
        signature += f":{primary_file.split('/')[-1]}"
    return {
        "title": title[:300],
        "error_message": error_message,
        "affected_files": files,
        "frames": frames[:15],
        "failing_tests": failing[:10],
        "primary_file": primary_file,
        "signature": signature[:256],
    }
