"""
bocchi AI - RAG (检索增强生成) 基础设施层
"""

from .backends.embedders import Embedder
from .backends.storages import (
    AbstractVectorRecord,
    StorageBackend,
    TortoiseStorageBackend,
)
from .builder import RAGBuilder
from .configs import RAGConfig
from .engine import ScopedRAGClient
from .models import BaseRecord, SearchResult

__all__ = [
    "AbstractVectorRecord",
    "BaseRecord",
    "Embedder",
    "RAGBuilder",
    "RAGConfig",
    "ScopedRAGClient",
    "SearchResult",
    "StorageBackend",
    "TortoiseStorageBackend",
]
