from __future__ import annotations
from langchain_core.embeddings import Embeddings


def get_embeddings() -> Embeddings:
    """Return an embeddings instance built from the current database config.

    Instantiated on every call so admin changes take effect immediately.
    """
    from app.models.settings import EmbeddingConfig

    config = EmbeddingConfig.query.first()
    if config is None:
        raise RuntimeError("No embedding configuration found. Run flask db upgrade and seed defaults.")

    match config.provider:
        case "ollama":
            from langchain_ollama import OllamaEmbeddings
            return OllamaEmbeddings(model=config.model_name)

        case "openai":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model=config.model_name, openai_api_key=config.api_key)

        case _:
            raise ValueError(f"Unsupported embedding provider: {config.provider!r}")
