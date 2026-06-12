from __future__ import annotations
from flask import current_app
from langchain_chroma import Chroma
from langchain_core.vectorstores import VectorStoreRetriever

from .embeddings_factory import get_embeddings


def get_vector_store() -> Chroma:
    """Return a ChromaDB collection bound to the current embedding model."""
    return Chroma(
        collection_name=current_app.config["CHROMA_COLLECTION_NAME"],
        embedding_function=get_embeddings(),
        persist_directory=current_app.config["CHROMA_PERSIST_DIR"],
    )


def get_retriever(k: int | None = None) -> VectorStoreRetriever:
    """Return a similarity retriever. k defaults to the value in ChunkConfig."""
    if k is None:
        from app.models.settings import ChunkConfig
        chunk_cfg = ChunkConfig.query.first()
        k = chunk_cfg.k_retrievals if chunk_cfg else 5

    return get_vector_store().as_retriever(search_kwargs={"k": k})
