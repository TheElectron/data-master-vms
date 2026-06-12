from __future__ import annotations
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.ingestion.fetchers.base import FetchedArticle


class Chunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @classmethod
    def from_config(cls) -> "Chunker":
        """Build a Chunker from the current ChunkConfig row."""
        from app.models.settings import ChunkConfig
        cfg = ChunkConfig.query.first()
        if cfg:
            return cls(chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap)
        return cls()

    def chunk(self, article: FetchedArticle) -> list[Document]:
        """Split article content into overlapping chunks, preserving metadata."""
        doc = Document(
            page_content=article.content,
            metadata={
                "title": article.title,
                "url": article.url,
                "published_at": article.published_at.isoformat() if article.published_at else "",
                "source_id": article.source_id or "",
            },
        )
        return self._splitter.split_documents([doc])
