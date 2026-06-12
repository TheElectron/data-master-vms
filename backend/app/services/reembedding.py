from __future__ import annotations
import logging

from app.extensions import db
from app.ingestion.fetchers.base import FetchedArticle
from app.ingestion.pipeline import _chunk_id
from app.ingestion.processors.chunker import Chunker
from app.models.settings import EmbeddingConfig, RawArticle
from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def run_reembedding() -> dict:
    """Clear ChromaDB and re-embed all stored articles with the current embedding model.

    Called when the admin switches the embedding model. The raw text in RawArticle is the
    source of truth, so no re-fetching from RSS is needed.
    """
    emb_cfg = EmbeddingConfig.query.first()
    new_model = emb_cfg.model_name if emb_cfg else "unknown"

    # Delete the collection and immediately recreate it with the new embedding model.
    # The two get_vector_store() calls are intentional: the first deletes, the second
    # creates a fresh collection bound to the updated EmbeddingConfig.
    get_vector_store().delete_collection()
    store = get_vector_store()

    chunker = Chunker.from_config()
    articles = RawArticle.query.all()

    processed = errors = 0
    for article in articles:
        try:
            fetched = FetchedArticle(
                title=article.title,
                url=article.url,
                content=article.content,
                published_at=article.published_at,
                source_id=article.source_id,
            )
            chunks = chunker.chunk(fetched)
            chunk_ids = [_chunk_id(article.url, i) for i in range(len(chunks))]
            store.add_documents(documents=chunks, ids=chunk_ids)

            article.embedding_model = new_model
            db.session.commit()
            processed += 1
        except Exception as exc:
            db.session.rollback()
            logger.error("Re-embedding failed for article %s: %s", article.url, exc)
            errors += 1

    logger.info("Re-embedding complete — processed=%d errors=%d model=%s", processed, errors, new_model)
    return {"processed": processed, "errors": errors, "new_model": new_model}


def run_reembedding_in_context(app) -> None:
    """APScheduler entry point. Pushes a Flask app context before running."""
    with app.app_context():
        try:
            run_reembedding()
        except Exception as exc:
            logger.error("Re-embedding job failed: %s", exc)
