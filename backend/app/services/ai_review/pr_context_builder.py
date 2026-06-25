from __future__ import annotations

from dataclasses import dataclass

from app.services.types import ChangedFile


@dataclass(frozen=True)
class PRContextLimits:
    max_files: int = 40
    max_patch_chars_per_file: int = 8000
    max_content_chars_per_file: int = 2000
    max_total_chars: int = 80000


class PRContextBuilder:
    def __init__(self, limits: PRContextLimits | None = None) -> None:
        self.limits = limits or PRContextLimits()

    def build(self, files: list[ChangedFile]) -> str:
        if not files:
            return "No changed files were available for AI review."

        sections = [
            "Pull request changed files summary:",
            f"Total files available: {len(files)}",
            "",
        ]
        included_files = files[: self.limits.max_files]
        for index, file in enumerate(included_files, start=1):
            patch = self._truncate(file.patch or "", self.limits.max_patch_chars_per_file)
            content_excerpt = self._truncate(file.content or "", self.limits.max_content_chars_per_file)
            section = [
                f"FILE {index}: {file.path}",
                f"Status: {file.status}",
                f"Additions: {file.additions}",
                f"Deletions: {file.deletions}",
                "Patch:",
                patch or "(no patch available)",
            ]
            if content_excerpt:
                section.extend(["Current file excerpt:", content_excerpt])
            sections.append("\n".join(section))

        if len(files) > len(included_files):
            sections.append(f"{len(files) - len(included_files)} additional files were omitted from the AI prompt.")

        return self._truncate("\n\n---\n\n".join(sections), self.limits.max_total_chars)

    def _truncate(self, value: str, max_chars: int) -> str:
        if len(value) <= max_chars:
            return value
        return f"{value[:max_chars]}\n...[truncated]"
