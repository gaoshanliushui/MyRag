"""
QA Chain (LCEL)

End-to-end Retrieval-Augmented Generation chain built with LangChain Expression
Language. Composes:

  question -> [EnsembleRetriever | passthrough]
            -> format context
            -> QA_PROMPT
            -> chat model
            -> StrOutputParser
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)

from app.core.chains.prompts import QA_PROMPT
from app.core.llm.factory import get_chat_model
from app.core.retrieval.ensemble import build_ensemble_retriever
from app.utils.logging import get_logger

logger = get_logger("core.chains.qa_chain")


def format_docs(docs: list) -> str:
    """Format a list of `Document`s into a single context string."""
    if not docs:
        return "（无相关参考文档）"
    parts: list[str] = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        page = meta.get("page_number")
        source = meta.get("source") or meta.get("document_id") or ""
        header = f"[{i}] (source={source}, page={page})" if source else f"[{i}]"
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def build_qa_chain(
    tenant: object,
    weights: dict[str, float] | None = None,
    top_k: int = 50,
) -> Runnable:
    """
    Build a LangChain LCEL chain for question answering.

    Args:
        tenant: ORM `Tenant` instance (provides per-tenant resource names).
        weights: Fusion weights (dense/sparse/graph). Defaults to 0.4/0.3/0.3.
        top_k: Per-channel candidate count.

    Returns:
        A `Runnable` taking a question `str` and returning the LLM answer `str`.
    """
    weights = weights or {"dense": 0.4, "sparse": 0.3, "graph": 0.3}
    ensemble = build_ensemble_retriever(tenant, weights, top_k=top_k)
    llm = get_chat_model()

    async def retrieve_docs(question: str) -> list:
        return await ensemble.ainvoke(question)

    retrieve = RunnableParallel(
        {
            "docs": RunnableLambda(retrieve_docs),
            "question": RunnablePassthrough(),
        }
    )
    inject_context = RunnableLambda(
        lambda payload: {
            "context": format_docs(payload["docs"]),
            "question": payload["question"],
        }
    )

    chain: Runnable = retrieve | inject_context | QA_PROMPT | llm | StrOutputParser()
    logger.info(
        f"QA chain built for tenant {getattr(tenant, 'id', '?')} with weights {weights}"
    )
    return chain