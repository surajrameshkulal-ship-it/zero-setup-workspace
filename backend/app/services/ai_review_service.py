from __future__ import annotations
from app.integrations.openai_client import OpenAIReviewClient
from app.services.types import ChangedFile


class AIReviewService:
    def __init__(self, client: OpenAIReviewClient | None = None) -> None:
        self.client = client or OpenAIReviewClient()

    def review_files(self, files: list[ChangedFile]) -> dict:
        return self.client.review_files(files)

