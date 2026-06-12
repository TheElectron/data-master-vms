from __future__ import annotations
import logging

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from .llm_factory import get_llm
from .vector_store import get_retriever

logger = logging.getLogger(__name__)


def _format_docs(docs: list[Document]) -> str:
    """Concatenate retrieved chunks into a single context block."""
    sections = []
    for doc in docs:
        title = doc.metadata.get("title", "Article")
        sections.append(f"[{title}]\n{doc.page_content}")
    return "\n\n---\n\n".join(sections)


def ask(question: str) -> dict:
    """Run the RAG pipeline and return the answer alongside source metadata.

    Retrieval and generation are kept as two explicit steps so source documents
    can be returned to the caller without a second DB round-trip.
    """
    from app.models.settings import LLMConfig

    llm_config = LLMConfig.query.first()
    system_prompt = llm_config.system_prompt if llm_config else "You are a helpful assistant."

    retriever = get_retriever()
    llm = get_llm()

    logger.debug("rag: retrieving docs for question=%r", question)
    docs: list[Document] = retriever.invoke(question)
    logger.info("rag: retrieved %d docs", len(docs))

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt + "\n\nContext:\n{context}"),
        ("human", "{question}"),
    ])

    chain = prompt | llm | StrOutputParser()
    logger.debug("rag: invoking LLM")
    answer: str = chain.invoke({
        "context": _format_docs(docs),
        "question": question,
    })
    logger.info("rag: answer generated (%d chars)", len(answer))

    sources = [
        {
            "title": doc.metadata.get("title", ""),
            "url": doc.metadata.get("url", ""),
            "published_at": doc.metadata.get("published_at", ""),
        }
        for doc in docs
    ]

    return {"answer": answer, "sources": sources}
