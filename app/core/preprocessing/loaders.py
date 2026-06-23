"""
Document Loader Routing

Unified entry point for loading documents of various formats via
LangChain `DocumentLoader`s.

Supported formats:
- PDF      → PyMuPDFLoader (or PyPDFLoader fallback)
- DOCX     → UnstructuredWordDocumentLoader
- TXT/MD   → TextLoader
- HTML     → BSHTMLLoader
"""

from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.config import settings
from app.utils.exceptions import DocumentProcessingError
from app.utils.logging import get_logger

logger = get_logger("core.preprocessing.loaders")


def load_document(file_path: str, file_type: str | None = None) -> list[Document]:
    """
    Load a document using the appropriate LangChain loader.

    Args:
        file_path: Path to the file.
        file_type: File extension (pdf, docx, txt, html, md). If None, inferred.

    Returns:
        List of LangChain `Document` objects (page_content + metadata).
    """
    path = Path(file_path)
    if not path.exists():
        raise DocumentProcessingError(path.name, "load", "File not found")

    ext = (file_type or path.suffix.lstrip(".")).lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise DocumentProcessingError(path.name, "load", f"Unsupported file type: {ext}")

    loader_cls = _LOADER_REGISTRY.get(ext)
    if loader_cls is None:
        raise DocumentProcessingError(path.name, "load", f"No loader registered for {ext}")

    logger.info(f"Loading document {path.name} with {loader_cls.__name__}")
    loader = loader_cls(str(path))
    docs = loader.load()

    # Normalise metadata: always use the basename for `source`
    for d in docs:
        d.metadata["source"] = path.name
        d.metadata["file_type"] = ext
    return docs


_LOADER_REGISTRY: dict[str, Any] = {}


def _register_loaders() -> dict[str, Any]:
    """Lazy registration of loaders so import errors don't break the whole module."""
    registry: dict[str, Any] = {}

    def _try_register(ext: str, import_fn: Any) -> None:
        try:
            registry[ext] = import_fn()
        except Exception as exc:  # pragma: no cover - import guard
            logger.warning(f"Loader for {ext} unavailable: {exc}")

    def _pymupdf_loader():
        from langchain_community.document_loaders import PyMuPDFLoader
        return PyMuPDFLoader

    def _pypdf_loader():
        from langchain_community.document_loaders import PyPDFLoader
        return PyPDFLoader

    def _docx_loader():
        from langchain_community.document_loaders import UnstructuredWordDocumentLoader
        return UnstructuredWordDocumentLoader

    def _text_loader():
        from langchain_community.document_loaders import TextLoader
        return TextLoader

    def _bshtml_loader():
        from langchain_community.document_loaders import BSHTMLLoader
        return BSHTMLLoader

    def _unstructured_html_loader():
        from langchain_community.document_loaders import UnstructuredHTMLLoader
        return UnstructuredHTMLLoader

    _try_register("pdf", _pymupdf_loader)
    _try_register("pdf-fallback", _pypdf_loader)
    _try_register("docx", _docx_loader)
    _try_register("txt", _text_loader)
    _try_register("md", _text_loader)
    _try_register("html", _bshtml_loader)
    _try_register("html-fallback", _unstructured_html_loader)
    return registry


_LOADER_REGISTRY.update(_register_loaders())


def get_supported_types() -> list[str]:
    """Return file types with registered loaders (excluding fallbacks)."""
    return [ext for ext in _LOADER_REGISTRY if "-" not in ext]