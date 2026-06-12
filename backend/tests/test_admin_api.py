from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.settings import ChunkConfig, EmbeddingConfig, LLMConfig, RawArticle, SourceConfig

ADMIN_HEADERS = {"X-Admin-Key": "changeme"}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAdminAuth:
    def test_returns_401_without_key(self, client):
        for method, path in [
            ("GET", "/api/admin/config"),
            ("PUT", "/api/admin/config/llm"),
            ("PUT", "/api/admin/config/embedding"),
            ("PUT", "/api/admin/config/chunk"),
            ("GET", "/api/admin/sources"),
            ("POST", "/api/admin/sources"),
        ]:
            resp = getattr(client, method.lower())(path, json={})
            assert resp.status_code == 401, f"{method} {path} should be 401"

    def test_returns_401_with_wrong_key(self, client):
        resp = client.get("/api/admin/config", headers={"X-Admin-Key": "wrong"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/config
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_returns_all_sections(self, client):
        resp = client.get("/api/admin/config", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "llm" in body and "embedding" in body and "chunk" in body

    def test_does_not_expose_api_keys(self, client):
        resp = client.get("/api/admin/config", headers=ADMIN_HEADERS)
        body = resp.get_json()
        assert "api_key" not in body["llm"]
        assert "api_key" not in body["embedding"]

    def test_returns_seeded_defaults(self, client):
        body = client.get("/api/admin/config", headers=ADMIN_HEADERS).get_json()
        assert body["llm"]["provider"] == "ollama"
        assert body["llm"]["model_name"] == "llama3.2"
        assert body["chunk"]["k_retrievals"] == 5


# ---------------------------------------------------------------------------
# PUT /api/admin/config/llm
# ---------------------------------------------------------------------------

class TestUpdateLLMConfig:
    def test_updates_provider_and_model(self, client):
        payload = {"provider": "openai", "model_name": "gpt-4o-mini", "temperature": 0.7}
        resp = client.put("/api/admin/config/llm", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["provider"] == "openai"
        assert body["model_name"] == "gpt-4o-mini"
        assert body["temperature"] == 0.7

    def test_stores_api_key_without_returning_it(self, client, app):
        payload = {"provider": "openai", "model_name": "gpt-4o", "api_key": "sk-secret"}
        client.put("/api/admin/config/llm", json=payload, headers=ADMIN_HEADERS)
        with app.app_context():
            cfg = LLMConfig.query.first()
            assert cfg.api_key == "sk-secret"

    def test_updates_system_prompt(self, client):
        payload = {"provider": "ollama", "model_name": "llama3.2", "system_prompt": "Be brief."}
        resp = client.put("/api/admin/config/llm", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["system_prompt"] == "Be brief."

    def test_invalid_provider_returns_422(self, client):
        resp = client.put(
            "/api/admin/config/llm",
            json={"provider": "gemini", "model_name": "gemini-pro"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422
        assert "provider" in resp.get_json()["errors"]

    def test_temperature_out_of_range_returns_422(self, client):
        resp = client.put(
            "/api/admin/config/llm",
            json={"provider": "ollama", "model_name": "llama3.2", "temperature": 5.0},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422

    def test_missing_model_name_returns_422(self, client):
        resp = client.put(
            "/api/admin/config/llm",
            json={"provider": "ollama"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422
        assert "model_name" in resp.get_json()["errors"]


# ---------------------------------------------------------------------------
# PUT /api/admin/config/chunk
# ---------------------------------------------------------------------------

class TestUpdateChunkConfig:
    def test_updates_all_params(self, client):
        payload = {"chunk_size": 500, "chunk_overlap": 50, "k_retrievals": 3}
        resp = client.put("/api/admin/config/chunk", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["chunk_size"] == 500
        assert body["chunk_overlap"] == 50
        assert body["k_retrievals"] == 3

    def test_overlap_exceeds_size_returns_422(self, client):
        resp = client.put(
            "/api/admin/config/chunk",
            json={"chunk_size": 200, "chunk_overlap": 300, "k_retrievals": 5},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422
        assert "chunk_overlap" in resp.get_json()["errors"]

    def test_k_retrievals_out_of_range_returns_422(self, client):
        resp = client.put(
            "/api/admin/config/chunk",
            json={"chunk_size": 1000, "chunk_overlap": 100, "k_retrievals": 100},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/admin/config/embedding
# ---------------------------------------------------------------------------

class TestUpdateEmbeddingConfig:
    def test_same_model_returns_200_no_reembedding(self, client):
        payload = {"provider": "ollama", "model_name": "mxbai-embed-large"}
        resp = client.put("/api/admin/config/embedding", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert "reembedding_triggered" not in resp.get_json()

    def test_model_change_with_no_articles_returns_200(self, client):
        # No RawArticle rows → re-embedding not needed even if model changes
        payload = {"provider": "openai", "model_name": "text-embedding-3-small"}
        resp = client.put("/api/admin/config/embedding", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 200

    def test_model_change_with_articles_triggers_reembedding(self, client, app):
        with app.app_context():
            db.session.add(RawArticle(
                title="T", url="https://x.com/1", content="content", embedding_model="mxbai-embed-large"
            ))
            db.session.commit()

        mock_job = MagicMock()
        mock_job.id = "reembed_test"
        with patch("app.api.admin.scheduler") as mock_sched:
            mock_sched.add_job.return_value = mock_job
            payload = {"provider": "openai", "model_name": "text-embedding-3-small"}
            resp = client.put("/api/admin/config/embedding", json=payload, headers=ADMIN_HEADERS)

        assert resp.status_code == 202
        body = resp.get_json()
        assert body["reembedding_triggered"] is True
        assert body["job_id"] == "reembed_test"

    def test_invalid_provider_returns_422(self, client):
        resp = client.put(
            "/api/admin/config/embedding",
            json={"provider": "anthropic", "model_name": "claude-embed"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Sources CRUD
# ---------------------------------------------------------------------------

class TestSourceEndpoints:
    def test_list_returns_seeded_sources(self, client):
        resp = client.get("/api/admin/sources", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        sources = resp.get_json()
        assert len(sources) == 4
        names = {s["name"] for s in sources}
        assert "TechCrunch" in names

    def test_create_source(self, client):
        payload = {"name": "My Feed", "url": "https://example.com/feed.rss"}
        resp = client.post("/api/admin/sources", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["name"] == "My Feed"
        assert body["active"] is True
        assert "id" in body

    def test_create_source_inactive(self, client):
        payload = {"name": "Paused", "url": "https://example.com/paused.rss", "active": False}
        resp = client.post("/api/admin/sources", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 201
        assert resp.get_json()["active"] is False

    def test_create_duplicate_url_returns_409(self, client):
        payload = {"name": "Dup", "url": "https://techcrunch.com/feed/"}
        resp = client.post("/api/admin/sources", json=payload, headers=ADMIN_HEADERS)
        assert resp.status_code == 409

    def test_create_missing_name_returns_422(self, client):
        resp = client.post(
            "/api/admin/sources",
            json={"url": "https://example.com/feed.rss"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422
        assert "name" in resp.get_json()["errors"]

    def test_create_invalid_url_returns_422(self, client):
        resp = client.post(
            "/api/admin/sources",
            json={"name": "Bad", "url": "not-a-url"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422

    def test_patch_toggles_active(self, client, app):
        with app.app_context():
            src_id = SourceConfig.query.first().id

        resp = client.patch(
            f"/api/admin/sources/{src_id}",
            json={"active": False},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False

    def test_patch_nonexistent_returns_404(self, client):
        resp = client.patch(
            "/api/admin/sources/99999",
            json={"active": False},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404

    def test_delete_source(self, client, app):
        with app.app_context():
            src_id = SourceConfig.query.first().id

        resp = client.delete(f"/api/admin/sources/{src_id}", headers=ADMIN_HEADERS)
        assert resp.status_code == 204

        resp2 = client.delete(f"/api/admin/sources/{src_id}", headers=ADMIN_HEADERS)
        assert resp2.status_code == 404

    def test_delete_nullifies_articles_source_id(self, client, app):
        with app.app_context():
            src = SourceConfig.query.first()
            src_id = src.id
            db.session.add(RawArticle(
                title="A", url="https://a.com/1", content="c",
                embedding_model="m", source_id=src_id,
            ))
            db.session.commit()

        client.delete(f"/api/admin/sources/{src_id}", headers=ADMIN_HEADERS)

        with app.app_context():
            article = RawArticle.query.filter_by(url="https://a.com/1").first()
            assert article is not None
            assert article.source_id is None

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/admin/sources/99999", headers=ADMIN_HEADERS)
        assert resp.status_code == 404
