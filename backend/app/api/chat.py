import logging

from flask import Blueprint, request, jsonify
from app.services.rag_service import ask

chat_bp = Blueprint("chat", __name__)
logger = logging.getLogger(__name__)


@chat_bp.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    question: str = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "Field 'question' is required and cannot be empty."}), 400

    logger.debug("chat: question=%r", question)
    try:
        result = ask(question)
        logger.debug("chat: answered with %d sources", len(result.get("sources", [])))
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("chat: unhandled error for question=%r", question)
        return jsonify({"error": str(exc)}), 500
