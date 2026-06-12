import logging
import os
import time

from flask import Flask, g, request
from .config import config_map
from .extensions import db, migrate, cors, scheduler

logger = logging.getLogger(__name__)


def create_app(env: str | None = None) -> Flask:
    """Application factory. Creates and configures the Flask app."""
    env = env or os.getenv("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_map[env])

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_request_hooks(app)

    with app.app_context():
        from . import models  # noqa: F401 — registers ORM models with SQLAlchemy metadata
        db.create_all()
        _seed_defaults()

    if not app.config.get("TESTING") and not scheduler.running:
        _register_scheduled_jobs(app)
        scheduler.start()

    return app


def _configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Reduce noise from chatty third-party libraries
    for noisy in ("werkzeug", "httpx", "httpcore", "chromadb", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def _before():
        g._t0 = time.monotonic()
        logger.info("→ %s %s", request.method, request.full_path.rstrip("?"))

    @app.after_request
    def _after(response):
        ms = (time.monotonic() - getattr(g, "_t0", time.monotonic())) * 1000
        logger.info("← %s %s  %d  %.0fms", request.method, request.path, response.status_code, ms)
        return response


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})


def _register_blueprints(app: Flask) -> None:
    from .api.chat import chat_bp
    from .api.admin import admin_bp
    from .api.ingestion import ingestion_bp
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(ingestion_bp, url_prefix="/api")


def _register_scheduled_jobs(app: Flask) -> None:
    from .ingestion.pipeline import run_pipeline_in_context
    scheduler.add_job(
        func=run_pipeline_in_context,
        args=[app],
        trigger="cron",
        day_of_week="sun",
        hour=0,
        minute=0,
        id="weekly_ingestion",
        replace_existing=True,
    )


def _seed_defaults() -> None:
    """Populate config tables with sensible defaults on first run."""
    # Import here to avoid circular imports at module load time
    from .models.settings import LLMConfig, EmbeddingConfig, ChunkConfig, SourceConfig

    if not LLMConfig.query.first():
        db.session.add(LLMConfig(
            provider="ollama",
            model_name="llama3.2",
            temperature=0.0,
            system_prompt=(
                "You are a helpful tech news assistant. "
                "Answer questions based solely on the provided context. "
                "If the context does not contain enough information to answer, "
                "say so clearly and do not fabricate facts."
            ),
        ))

    if not EmbeddingConfig.query.first():
        db.session.add(EmbeddingConfig(
            provider="ollama",
            model_name="mxbai-embed-large",
        ))

    if not ChunkConfig.query.first():
        db.session.add(ChunkConfig(
            chunk_size=1000,
            chunk_overlap=100,
            k_retrievals=5,
        ))

    if not SourceConfig.query.first():
        default_sources = [
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
            {"name": "Hacker News (Top)", "url": "https://hnrss.org/frontpage"},
        ]
        for src in default_sources:
            db.session.add(SourceConfig(**src))

    db.session.commit()
