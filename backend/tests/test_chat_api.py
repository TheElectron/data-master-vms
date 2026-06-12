from unittest.mock import patch


class TestChatEndpoint:
    def test_missing_body_returns_400(self, client):
        resp = client.post("/api/chat", content_type="application/json", data="")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_empty_question_returns_400(self, client):
        resp = client.post("/api/chat", json={"question": "   "})
        assert resp.status_code == 400
        assert "question" in resp.get_json()["error"].lower()

    def test_valid_question_returns_200(self, client):
        mock_result = {
            "answer": "This is a mocked answer.",
            "sources": [{"title": "Test Article", "url": "https://example.com", "published_at": ""}],
        }
        with patch("app.api.chat.ask", return_value=mock_result) as mock_ask:
            resp = client.post("/api/chat", json={"question": "What is AI?"})
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["answer"] == "This is a mocked answer."
            assert len(body["sources"]) == 1
            mock_ask.assert_called_once_with("What is AI?")

    def test_service_exception_returns_500(self, client):
        with patch("app.api.chat.ask", side_effect=RuntimeError("ChromaDB unavailable")):
            resp = client.post("/api/chat", json={"question": "What is AI?"})
            assert resp.status_code == 500
            assert "ChromaDB unavailable" in resp.get_json()["error"]
