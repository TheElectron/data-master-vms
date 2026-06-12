from datetime import datetime, timezone
from app.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LLMConfig(db.Model):
    __tablename__ = "llm_config"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)    # ollama | openai | anthropic
    model_name = db.Column(db.String(100), nullable=False)
    temperature = db.Column(db.Float, default=0.0, nullable=False)
    api_key = db.Column(db.String(255), nullable=True)     # null for local models
    system_prompt = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "system_prompt": self.system_prompt,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EmbeddingConfig(db.Model):
    __tablename__ = "embedding_config"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)    # ollama | openai
    model_name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "model_name": self.model_name,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChunkConfig(db.Model):
    __tablename__ = "chunk_config"

    id = db.Column(db.Integer, primary_key=True)
    chunk_size = db.Column(db.Integer, default=1000, nullable=False)
    chunk_overlap = db.Column(db.Integer, default=100, nullable=False)
    k_retrievals = db.Column(db.Integer, default=5, nullable=False)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "k_retrievals": self.k_retrievals,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SourceConfig(db.Model):
    __tablename__ = "source_config"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_now)

    articles = db.relationship("RawArticle", back_populates="source")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IngestionRun(db.Model):
    """Tracks every pipeline execution for status monitoring."""

    __tablename__ = "ingestion_run"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    # running | completed | failed
    status = db.Column(db.String(20), default="running", nullable=False)
    fetched = db.Column(db.Integer, default=0)
    skipped = db.Column(db.Integer, default=0)
    errors = db.Column(db.Integer, default=0)
    embedding_model = db.Column(db.String(100), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "fetched": self.fetched,
            "skipped": self.skipped,
            "errors": self.errors,
            "embedding_model": self.embedding_model,
            "error_message": self.error_message,
        }


class RawArticle(db.Model):
    """Stores raw article text so embeddings can be regenerated on model changes."""

    __tablename__ = "raw_article"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    content = db.Column(db.Text, nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
    ingested_at = db.Column(db.DateTime, default=_now)
    # Tracks which embedding model produced the current ChromaDB vectors for this article.
    # When this differs from EmbeddingConfig.model_name, the article needs re-embedding.
    embedding_model = db.Column(db.String(100), nullable=True)
    source_id = db.Column(db.Integer, db.ForeignKey("source_config.id"), nullable=True)

    source = db.relationship("SourceConfig", back_populates="articles")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "embedding_model": self.embedding_model,
            "source_id": self.source_id,
        }
