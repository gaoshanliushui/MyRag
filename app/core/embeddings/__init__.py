"""LangChain-compatible embeddings module."""

from app.core.embeddings.bge_m3 import BGE_M3_Embeddings, get_bge_m3

__all__ = ["BGE_M3_Embeddings", "get_bge_m3"]