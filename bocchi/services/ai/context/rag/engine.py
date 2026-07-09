from typing import Any

from bocchi.services.ai.context.rag.backends import (
    StorageBackend,
)
from bocchi.services.ai.context.rag.configs import RAGConfig
from bocchi.services.ai.context.rag.ingestion import (
    IndexPipeline,
)
from bocchi.services.ai.context.rag.models import (
    BaseRecord,
    SearchResult,
)
from bocchi.services.ai.context.rag.retrieval import (
    BaseRetriever,
)
from bocchi.services.ai.utils.scope import normalize_scope_path


class ScopedRAGClient:
    """
    RAG 基础设施门面。
    封装了存储后端、检索器和写入管线，将所有操作透明地限定在指定的作用域前缀下。
    """

    def __init__(
        self,
        storage: StorageBackend,
        retriever: BaseRetriever,
        pipeline: IndexPipeline,
        scopes: str | list[str] = "/",
        config: RAGConfig | None = None,
    ):
        """
        初始化 ScopedRAGClient 实例。

        参数:
            storage: 底层向量/文档存储后端。
            retriever: 数据召回检索器。
            pipeline: 数据入库和索引分块处理管线。
            scopes: 数据隔离作用域，支持单作用域前缀或多作用域前缀列表。
            config: 全局的 RAG 配置项。
        """
        self.storage = storage
        self.retriever = retriever
        self.pipeline = pipeline
        self.config = config or RAGConfig()
        self._background_tasks = set()
        if isinstance(scopes, str):
            self.scopes = [normalize_scope_path(scopes)]
        else:
            self.scopes = [normalize_scope_path(s) for s in scopes]

        self.scope_prefix = self.scopes[0] if self.scopes else "/"

    async def ingest(self, records: list[BaseRecord]) -> int:
        """通过 RAG Ingestion Pipeline 处理并入库数据"""
        for r in records:
            if "scope" not in r.metadata:
                r.metadata["scope"] = self.scope_prefix

        res = await self.pipeline.run(records)
        return len(res)

    async def search(
        self,
        query: Any,
        limit: int = 10,
        scopes: str | list[str] | None = None,
        **kwargs: Any,
    ) -> list[SearchResult]:
        """
        多作用域联合切片视图检索 (Union Search)。
        并发向多个独立的作用域发起检索，并对结果进行合并、去重和重排。
        """
        target_scopes = self.scopes
        if scopes is not None:
            target_scopes = (
                [normalize_scope_path(scopes)]
                if isinstance(scopes, str)
                else [normalize_scope_path(s) for s in scopes]
            )

        if not target_scopes:
            return []

        kwargs["scopes"] = target_scopes
        return await self.retriever.retrieve(query, limit=limit, **kwargs)

    async def update(self, record: BaseRecord) -> None:
        record.metadata["scope"] = self.scope_prefix
        await self.storage.update(record)

    async def delete(self, record_ids: list[str] | None = None, **kwargs: Any) -> int:
        kwargs["scope_prefix"] = self.scope_prefix
        return await self.storage.delete(record_ids=record_ids, **kwargs)
