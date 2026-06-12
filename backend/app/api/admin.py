from __future__ import annotations
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from marshmallow import ValidationError

from app.extensions import db, scheduler
from app.models.settings import ChunkConfig, EmbeddingConfig, LLMConfig, RawArticle, SourceConfig
from app.schemas.admin import (
    ChunkConfigUpdateSchema,
    EmbeddingConfigUpdateSchema,
    LLMConfigUpdateSchema,
    SourceConfigCreateSchema,
    SourceConfigUpdateSchema,
)

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

_llm_schema = LLMConfigUpdateSchema()
_emb_schema = EmbeddingConfigUpdateSchema()
_chunk_schema = ChunkConfigUpdateSchema()
_src_create_schema = SourceConfigCreateSchema()
_src_update_schema = SourceConfigUpdateSchema()


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def require_admin_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get("X-Admin-Key", "") != current_app.config["ADMIN_API_KEY"]:
            return jsonify({"error": "Unauthorized. Provide a valid X-Admin-Key header."}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(schema, payload: dict):
    """Validate payload. Returns (data, None) on success, (None, error_response) on failure."""
    try:
        return schema.load(payload), None
    except ValidationError as exc:
        return None, (jsonify({"errors": exc.messages}), 422)


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

@admin_bp.route("/admin/config", methods=["GET"])
@require_admin_key
def get_config():
    return jsonify({
        "llm": LLMConfig.query.first().to_dict(),
        "embedding": EmbeddingConfig.query.first().to_dict(),
        "chunk": ChunkConfig.query.first().to_dict(),
    }), 200


@admin_bp.route("/admin/config/llm", methods=["PUT"])
@require_admin_key
def update_llm_config():
    data, err = _load(_llm_schema, request.get_json(silent=True) or {})
    if err:
        return err

    cfg = LLMConfig.query.first()
    cfg.provider = data["provider"]
    cfg.model_name = data["model_name"]
    cfg.temperature = data["temperature"]
    if data["api_key"] is not None:
        cfg.api_key = data["api_key"]
    if data["system_prompt"] is not None:
        cfg.system_prompt = data["system_prompt"]

    db.session.commit()
    logger.info("llm config updated: provider=%s model=%s", cfg.provider, cfg.model_name)
    return jsonify(cfg.to_dict()), 200


@admin_bp.route("/admin/config/embedding", methods=["PUT"])
@require_admin_key
def update_embedding_config():
    data, err = _load(_emb_schema, request.get_json(silent=True) or {})
    if err:
        return err

    cfg = EmbeddingConfig.query.first()
    model_changed = (cfg.provider != data["provider"] or cfg.model_name != data["model_name"])

    cfg.provider = data["provider"]
    cfg.model_name = data["model_name"]
    if data["api_key"] is not None:
        cfg.api_key = data["api_key"]

    db.session.commit()
    logger.info(
        "embedding config updated: provider=%s model=%s model_changed=%s",
        cfg.provider, cfg.model_name, model_changed,
    )

    if model_changed and RawArticle.query.count() > 0:
        from app.services.reembedding import run_reembedding_in_context
        app = current_app._get_current_object()
        job = scheduler.add_job(
            func=run_reembedding_in_context,
            args=[app],
            trigger="date",
            run_date=datetime.now(timezone.utc),
            id=f"reembed_{int(datetime.now(timezone.utc).timestamp())}",
            misfire_grace_time=600,
        )
        logger.info("re-embedding job queued: job_id=%s", job.id)
        return jsonify({**cfg.to_dict(), "reembedding_triggered": True, "job_id": job.id}), 202

    return jsonify(cfg.to_dict()), 200


@admin_bp.route("/admin/config/chunk", methods=["PUT"])
@require_admin_key
def update_chunk_config():
    data, err = _load(_chunk_schema, request.get_json(silent=True) or {})
    if err:
        return err

    cfg = ChunkConfig.query.first()
    cfg.chunk_size = data["chunk_size"]
    cfg.chunk_overlap = data["chunk_overlap"]
    cfg.k_retrievals = data["k_retrievals"]
    db.session.commit()
    return jsonify(cfg.to_dict()), 200


# ---------------------------------------------------------------------------
# Sources endpoints
# ---------------------------------------------------------------------------

@admin_bp.route("/admin/sources", methods=["GET"])
@require_admin_key
def list_sources():
    sources = SourceConfig.query.order_by(SourceConfig.id).all()
    return jsonify([s.to_dict() for s in sources]), 200


@admin_bp.route("/admin/sources", methods=["POST"])
@require_admin_key
def create_source():
    data, err = _load(_src_create_schema, request.get_json(silent=True) or {})
    if err:
        return err

    if SourceConfig.query.filter_by(url=data["url"]).first():
        return jsonify({"error": "A source with this URL already exists."}), 409

    src = SourceConfig(name=data["name"], url=data["url"], active=data["active"])
    db.session.add(src)
    db.session.commit()
    return jsonify(src.to_dict()), 201


@admin_bp.route("/admin/sources/<int:source_id>", methods=["PATCH"])
@require_admin_key
def update_source(source_id: int):
    src = db.session.get(SourceConfig, source_id)
    if src is None:
        return jsonify({"error": "Source not found."}), 404

    data, err = _load(_src_update_schema, request.get_json(silent=True) or {})
    if err:
        return err

    if "name" in data:
        src.name = data["name"]
    if "url" in data:
        src.url = data["url"]
    if "active" in data:
        src.active = data["active"]

    db.session.commit()
    return jsonify(src.to_dict()), 200


@admin_bp.route("/admin/sources/<int:source_id>", methods=["DELETE"])
@require_admin_key
def delete_source(source_id: int):
    src = db.session.get(SourceConfig, source_id)
    if src is None:
        return jsonify({"error": "Source not found."}), 404

    # Nullify FK on related raw articles before removing the source row
    RawArticle.query.filter_by(source_id=source_id).update({"source_id": None})
    db.session.delete(src)
    db.session.commit()
    return "", 204
