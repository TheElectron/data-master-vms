from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models.settings import EmbeddingConfig, IngestionRun, RawArticle, SourceConfig
from app.services.vector_store import get_vector_store
from .fetchers.rss_fetcher import RSSFetcher
from .processors.chunker import Chunker

logger = logging.getLogger(__name__)


def _chunk_id(url: str, index: int) -> str:
    """Deterministic chunk ID so re-processing the same article never creates duplicates."""
    return hashlib.sha256(f"{url}:{index}".encode()).hexdigest()


def run_pipeline() -> dict:
    """Fetch → chunk → embed → persist.

    Creates an IngestionRun record at the start and updates it on completion or failure.
    Returns a summary dict on success; raises on unrecoverable errors.
    """
    run = IngestionRun(status="running", started_at=datetime.now(timezone.utc))
    db.session.add(run)
    db.session.commit()
    run_id = run.id

    fetched = skipped = errors = 0
    embedding_model = "unknown"

    try:
        emb_cfg = EmbeddingConfig.query.first()
        embedding_model = emb_cfg.model_name if emb_cfg else "unknown"

        chunker = Chunker.from_config()
        vector_store = get_vector_store()
        sources = SourceConfig.query.filter_by(active=True).all()

        for source in sources:
            logger.info("Fetching source: %s", source.name)
            try:
                articles = RSSFetcher(source).fetch()
            except Exception as exc:
                logger.error("Failed to fetch source %s: %s", source.name, exc)
                errors += 1
                continue

            for article in articles:
                if not article.content.strip():
                    skipped += 1
                    continue

                if RawArticle.query.filter_by(url=article.url).first():
                    skipped += 1
                    continue

                try:
                    chunks = chunker.chunk(article)
                    chunk_ids = [_chunk_id(article.url, i) for i in range(len(chunks))]
                    vector_store.add_documents(documents=chunks, ids=chunk_ids)

                    db.session.add(RawArticle(
                        title=article.title,
                        url=article.url,
                        content=article.content,
                        published_at=article.published_at,
                        source_id=article.source_id,
                        embedding_model=embedding_model,
                    ))
                    db.session.commit()
                    fetched += 1
                    logger.debug("Ingested: %s", article.title)

                except Exception as exc:
                    db.session.rollback()
                    logger.error("Failed to ingest article %s: %s", article.url, exc)
                    errors += 1

        _finish_run(run_id, "completed", fetched, skipped, errors, embedding_model)
        return {
            "status": "completed",
            "fetched": fetched,
            "skipped": skipped,
            "errors": errors,
            "embedding_model": embedding_model,
        }

    except Exception as exc:
        _finish_run(run_id, "failed", fetched, skipped, errors, embedding_model, str(exc))
        raise


def _finish_run(
    run_id: int,
    status: str,
    fetched: int,
    skipped: int,
    errors: int,
    embedding_model: str,
    error_message: str | None = None,
) -> None:
    run = db.session.get(IngestionRun, run_id)
    if run is None:
        return
    run.status = status
    run.completed_at = datetime.now(timezone.utc)
    run.fetched = fetched
    run.skipped = skipped
    run.errors = errors
    run.embedding_model = embedding_model
    run.error_message = error_message
    db.session.commit()


def run_pipeline_in_context(app) -> None:
    """APScheduler entry point. Pushes a Flask app context before running."""
    with app.app_context():
        try:
            result = run_pipeline()
            logger.info("Scheduled ingestion finished: %s", result)
        except Exception as exc:
            logger.error("Scheduled ingestion failed: %s", exc)
