from unittest.mock import patch, MagicMock
import pytest
from app.models.settings import LLMConfig
from app.extensions import db


class TestLLMFactory:
    def test_get_llm_raises_when_no_config(self, app):
        with app.app_context():
            LLMConfig.query.delete()
            db.session.commit()
            from app.services.llm_factory import get_llm
            with pytest.raises(RuntimeError, match="No LLM configuration"):
                get_llm()

    def test_get_llm_ollama(self, app):
        with app.app_context():
            mock_instance = MagicMock()
            with patch("langchain_ollama.ChatOllama", return_value=mock_instance) as mock_cls:
                from app.services.llm_factory import get_llm
                result = get_llm()
                mock_cls.assert_called_once_with(model="llama3.2", temperature=0.0)
                assert result is mock_instance

    def test_get_llm_openai(self, app):
        with app.app_context():
            cfg = LLMConfig.query.first()
            cfg.provider = "openai"
            cfg.model_name = "gpt-4o-mini"
            cfg.api_key = "sk-test"
            db.session.commit()

            mock_instance = MagicMock()
            with patch("langchain_openai.ChatOpenAI", return_value=mock_instance) as mock_cls:
                from app.services.llm_factory import get_llm
                result = get_llm()
                mock_cls.assert_called_once_with(
                    model="gpt-4o-mini", temperature=0.0, openai_api_key="sk-test"
                )
                assert result is mock_instance

    def test_get_llm_raises_on_unknown_provider(self, app):
        with app.app_context():
            cfg = LLMConfig.query.first()
            cfg.provider = "unknown_provider"
            db.session.commit()
            from app.services.llm_factory import get_llm
            with pytest.raises(ValueError, match="Unsupported LLM provider"):
                get_llm()
