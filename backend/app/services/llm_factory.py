from __future__ import annotations
import logging

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


def get_llm() -> BaseChatModel:
    """Return an LLM instance built from the current database config.

    Instantiated on every request so admin changes take effect immediately.
    """
    from app.models.settings import LLMConfig

    config = LLMConfig.query.first()
    if config is None:
        raise RuntimeError("No LLM configuration found. Run flask db upgrade and seed defaults.")

    logger.debug("llm_factory: provider=%s model=%s", config.provider, config.model_name)

    match config.provider:
        case "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(model=config.model_name, temperature=config.temperature)

        case "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model_name,
                temperature=config.temperature,
                openai_api_key=config.api_key,
            )

        case "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=config.model_name,
                temperature=config.temperature,
                anthropic_api_key=config.api_key,
            )

        case _:
            raise ValueError(f"Unsupported LLM provider: {config.provider!r}")
