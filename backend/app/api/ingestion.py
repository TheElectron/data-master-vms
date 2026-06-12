import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from app.extensions import scheduler
from app.models.settings import IngestionRun, RawArticle

ingestion_bp = Blueprint("ingestion", __name__)
logger = logging.getLogger(__name__)


@ingestion_bp.route("/ingest/trigger", methods=["POST"])
def trigger_ingestion():
    """Schedule an immediate ingestion run in the background.

    Returns 409 if a run is already in progress.
    Returns 202 with the run details once the job is queued.
    """
    if IngestionRun.query.filter_by(status="running").first():
        return jsonify({"error": "An ingestion run is already in progress."}), 409

    from app.ingestion.pipeline import run_pipeline_in_context

    app = current_app._get_current_object()
    job = scheduler.add_job(
        func=run_pipeline_in_context,
        args=[app],
        trigger="date",
        run_date=datetime.now(timezone.utc),
        id=f"manual_{int(datetime.now(timezone.utc).timestamp())}",
        misfire_grace_time=300,
    )
    logger.info("manual ingestion queued: job_id=%s", job.id)
    return jsonify({"message": "Ingestion triggered.", "job_id": job.id}), 202


@ingestion_bp.route("/ingest/status", methods=["GET"])
def ingestion_status():
    """Return the last run summary, total article count, and next scheduled run."""
    last_run = (
        IngestionRun.query
        .order_by(IngestionRun.started_at.desc())
        .first()
    )

    total_articles = RawArticle.query.count()

    next_run: str | None = None
    weekly_job = scheduler.get_job("weekly_ingestion")
    if weekly_job and weekly_job.next_run_time:
        next_run = weekly_job.next_run_time.isoformat()

    return jsonify({
        "total_articles": total_articles,
        "next_scheduled_run": next_run,
        "last_run": last_run.to_dict() if last_run else None,
    }), 200
