from __future__ import annotations


class AIReviewPromptBuilder:
    def build(self, *, pr_context: str) -> str:
        return "\n\n".join(
            [
                (
                    "You are CodeDNA AI, a senior software engineering reviewer. "
                    "Review this pull request diff for a corporate engineering team."
                ),
                (
                    "Return strict JSON only. Do not wrap it in Markdown. "
                    "Use this schema exactly: "
                    "{"
                    "\"summary\": string, "
                    "\"security_issues\": string[], "
                    "\"bug_risks\": string[], "
                    "\"performance_concerns\": string[], "
                    "\"maintainability_suggestions\": string[], "
                    "\"recommended_action\": string, "
                    "\"findings\": ["
                    "{"
                    "\"path\": string|null, "
                    "\"line\": number|null, "
                    "\"severity\": \"low\"|\"medium\"|\"high\"|\"critical\", "
                    "\"title\": string, "
                    "\"description\": string, "
                    "\"recommendation\": string, "
                    "\"category\": \"security\"|\"bug\"|\"performance\"|\"maintainability\""
                    "}"
                    "]"
                    "}"
                ),
                (
                    "Keep each section practical and concise. Prefer real risks grounded in the diff. "
                    "If there are no issues for a section, return an empty array for that section."
                ),
                pr_context,
            ]
        )
