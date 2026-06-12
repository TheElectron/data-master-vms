from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchedArticle:
    title: str
    url: str
    content: str
    published_at: datetime | None = None
    source_id: int | None = None


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self) -> list[FetchedArticle]:
        """Fetch articles from the source and return them as FetchedArticle objects."""
        ...
