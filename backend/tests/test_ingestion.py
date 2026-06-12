from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.ingestion.fetchers.base import FetchedArticle
from app.ingestion.fetchers.rss_fetcher import RSSFetcher, _strip_html, _best_content
from app.ingestion.processors.chunker import Chunker
from app.models.settings import IngestionRun, RawArticle, SourceConfig


# ---------------------------------------------------------------------------
# HTML stripping helpers
# ---------------------------------------------------------------------------

class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert _strip_html("&amp; &lt;tag&gt;") == "& <tag>"

    def test_normalises_whitespace(self):
        assert _strip_html("a   \n\n  b") == "a b"


# ---------------------------------------------------------------------------
# RSSFetcher
# ---------------------------------------------------------------------------

def _make_entry(title="AI News", link="https://example.com/1", summary="Summary text"):
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.summary = summary
    entry.content = []          # no full-text content
    entry.published_parsed = (2026, 6, 10, 12, 0, 0, 0, 0, 0)
    return entry


class TestRSSFetcher:
    def _make_source(self, url="https://example.com/feed"):
        src = MagicMock()
        src.url = url
        src.id = 1
        src.name = "Test Feed"
        return src

    def test_fetch_returns_articles(self):
        source = self._make_source()
        feed = MagicMock()
        feed.entries = [_make_entry()]

        with patch("app.ingestion.fetchers.rss_fetcher.feedparser.parse", return_value=feed):
            articles = RSSFetcher(source).fetch()

        assert len(articles) == 1
        assert articles[0].title == "AI News"
        assert articles[0].url == "https://example.com/1"
        assert articles[0].content == "Summary text"
        assert articles[0].source_id == 1

    def test_skips_entries_without_url(self):
        source = self._make_source()
        feed = MagicMock()
        feed.entries = [_make_entry(link="")]

        with patch("app.ingestion.fetchers.rss_fetcher.feedparser.parse", return_value=feed):
            articles = RSSFetcher(source).fetch()

        assert articles == []

    def test_skips_entries_without_content(self):
        source = self._make_source()
        feed = MagicMock()
        entry = _make_entry(summary="")
        entry.content = []
        feed.entries = [entry]

        with patch("app.ingestion.fetchers.rss_fetcher.feedparser.parse", return_value=feed):
            articles = RSSFetcher(source).fetch()

        assert articles == []

    def test_prefers_full_content_over_summary(self):
        source = self._make_source()
        feed = MagicMock()
        entry = _make_entry(summary="Short summary")
        entry.content = [{"value": "<p>Full article text</p>"}]
        feed.entries = [entry]

        with patch("app.ingestion.fetchers.rss_fetcher.feedparser.parse", return_value=feed):
            articles = RSSFetcher(source).fetch()

        assert articles[0].content == "Full article text"


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

class TestChunker:
    def test_chunks_long_content(self):
        article = FetchedArticle(
            title="Test",
            url="https://example.com",
            content="word " * 500,   # 2500 chars → multiple chunks at size=1000
        )
        chunks = Chunker(chunk_size=1000, chunk_overlap=50).chunk(article)
        assert len(chunks) > 1

    def test_short_content_produces_single_chunk(self):
        article = FetchedArticle(
            title="Short",
            url="https://example.com/s",
            content="Brief summary.",
        )
        chunks = Chunker(chunk_size=1000, chunk_overlap=100).chunk(article)
        assert len(chunks) == 1

    def test_metadata_preserved_on_every_chunk(self):
        article = FetchedArticle(
            title="Meta Test",
            url="https://example.com/m",
            content="word " * 500,
            published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        )
        chunks = Chunker(chunk_size=500, chunk_overlap=50).chunk(article)
        for chunk in chunks:
            assert chunk.metadata["title"] == "Meta Test"
            assert chunk.metadata["url"] == "https://example.com/m"
            assert "2026-06-10" in chunk.metadata["published_at"]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def _seed_source(self, app):
        with app.app_context():
            # Remove seed defaults so the pipeline sees exactly one source
            SourceConfig.query.delete()
            src = SourceConfig(name="Test Feed", url="https://test.com/feed", active=True)
            db.session.add(src)
            db.session.commit()
            return src.id

    def test_creates_ingestion_run_record(self, app):
        source_id = self._seed_source(app)
        article = FetchedArticle(
            title="T1", url="https://t.com/1", content="content text", source_id=source_id
        )

        mock_store = MagicMock()

        with app.app_context():
            with (
                patch("app.ingestion.pipeline.RSSFetcher") as mock_fetcher_cls,
                patch("app.ingestion.pipeline.get_vector_store", return_value=mock_store),
            ):
                mock_fetcher_cls.return_value.fetch.return_value = [article]
                from app.ingestion.pipeline import run_pipeline
                result = run_pipeline()

            assert result["status"] == "completed"
            assert result["fetched"] == 1
            run = IngestionRun.query.order_by(IngestionRun.id.desc()).first()
            assert run.status == "completed"
            assert run.fetched == 1

    def test_skips_duplicate_urls(self, app):
        source_id = self._seed_source(app)
        article = FetchedArticle(
            title="Dup", url="https://t.com/dup", content="content", source_id=source_id
        )

        mock_store = MagicMock()

        with app.app_context():
            # Pre-insert the article so the pipeline skips it
            db.session.add(RawArticle(
                title="Dup", url="https://t.com/dup",
                content="content", embedding_model="mxbai-embed-large",
            ))
            db.session.commit()

            with (
                patch("app.ingestion.pipeline.RSSFetcher") as mock_fetcher_cls,
                patch("app.ingestion.pipeline.get_vector_store", return_value=mock_store),
            ):
                mock_fetcher_cls.return_value.fetch.return_value = [article]
                from app.ingestion.pipeline import run_pipeline
                result = run_pipeline()

            assert result["fetched"] == 0
            assert result["skipped"] == 1
            mock_store.add_documents.assert_not_called()

    def test_handles_fetch_error_gracefully(self, app):
        self._seed_source(app)
        mock_store = MagicMock()

        with app.app_context():
            with (
                patch("app.ingestion.pipeline.RSSFetcher") as mock_fetcher_cls,
                patch("app.ingestion.pipeline.get_vector_store", return_value=mock_store),
            ):
                mock_fetcher_cls.return_value.fetch.side_effect = ConnectionError("timeout")
                from app.ingestion.pipeline import run_pipeline
                result = run_pipeline()

            assert result["status"] == "completed"
            assert result["errors"] == 1
            assert result["fetched"] == 0


# ---------------------------------------------------------------------------
# Ingestion API endpoints
# ---------------------------------------------------------------------------

class TestIngestionEndpoints:
    def test_status_returns_200(self, client):
        resp = client.get("/api/ingest/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "total_articles" in body
        assert "last_run" in body

    def test_trigger_returns_409_when_run_in_progress(self, app, client):
        with app.app_context():
            db.session.add(IngestionRun(status="running"))
            db.session.commit()

        resp = client.post("/api/ingest/trigger")
        assert resp.status_code == 409
        assert "in progress" in resp.get_json()["error"].lower()

    def test_trigger_returns_202_when_scheduler_available(self, client):
        mock_job = MagicMock()
        mock_job.id = "manual_123"

        with patch("app.api.ingestion.scheduler") as mock_scheduler:
            mock_scheduler.add_job.return_value = mock_job
            resp = client.post("/api/ingest/trigger")

        assert resp.status_code == 202
        body = resp.get_json()
        assert body["job_id"] == "manual_123"
