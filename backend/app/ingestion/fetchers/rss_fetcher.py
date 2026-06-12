from __future__ import annotations
import html
import re
from datetime import datetime, timezone

import feedparser

from .base import BaseFetcher, FetchedArticle


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities, then normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def _parse_published(entry) -> datetime | None:
    """Convert feedparser's struct_time to an aware datetime, or return None."""
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if t is None:
        return None
    try:
        return datetime(*t[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _best_content(entry) -> str:
    """Return the richest text content available in the feed entry."""
    # Some feeds (e.g. full-text RSS) populate entry.content
    content_list = getattr(entry, "content", None)
    if content_list:
        return _strip_html(content_list[0].get("value", ""))

    # Fall back to the summary (most common)
    summary = getattr(entry, "summary", "") or ""
    return _strip_html(summary)


class RSSFetcher(BaseFetcher):
    def __init__(self, source) -> None:
        """
        Args:
            source: a SourceConfig instance (provides .url, .id, .name)
        """
        self._source = source

    def fetch(self) -> list[FetchedArticle]:
        """Parse the RSS feed and return one FetchedArticle per entry."""
        feed = feedparser.parse(self._source.url)

        articles: list[FetchedArticle] = []
        for entry in feed.entries:
            title = _strip_html(getattr(entry, "title", "") or "")
            url = getattr(entry, "link", "") or ""
            content = _best_content(entry)

            # Skip entries without a URL or any content
            if not url or not content:
                continue

            articles.append(FetchedArticle(
                title=title,
                url=url,
                content=content,
                published_at=_parse_published(entry),
                source_id=self._source.id,
            ))

        return articles
