"""
rag.py — Legacy shim. ChromaDB has been replaced by FAISS (systems/semantic_index.py).

This module is kept for API compatibility. All new code should use:
  - tools.index_storage.update_file_index  (incremental update + FAISS sync)
  - tools.index_storage.search_index       (hybrid AST + semantic search)
  - systems.semantic_index.sync_faiss_with_ast  (full rebuild)
"""
from systems.semantic_index import sync_faiss_with_ast
from tools.index_storage import update_file_index
from core.logger import get_logger

logger = get_logger(__name__)


def add_file_to_rag(path):
    """Deprecated: use update_file_index(path) directly."""
    logger.debug(f"add_file_to_rag called for {path} — routing to update_file_index")
    update_file_index(path)


def search_rag(query, top_k=3):
    """Deprecated: use tools.index_storage.search_index(query) directly."""
    from tools.index_storage import search_index
    return search_index(query)


def rebuild_rag():
    """Full rebuild of FAISS index from current AST index."""
    logger.info("Rebuilding FAISS index from AST index...")
    sync_faiss_with_ast()
    logger.info("FAISS index rebuilt.")