from abc import ABC, abstractmethod
from collections.abc import Sequence

from bocchi.services.ai.context.memory.types import (
    MemorySlot,
    SessionMetadata,
)
from bocchi.services.ai.core.messages import AgentMessage, LLMMessage
from bocchi.services.ai.run.context import RunContext
from bocchi.services.ai.utils.scope import ScopeSelector


class BaseChatContext(ABC):
    """短期对话历史记忆接口"""

    @abstractmethod
    async def get_messages(self, session: SessionMetadata) -> list[LLMMessage]:
        """获取当前会话的所有历史消息。"""
        ...

    @abstractmethod
    async def search(
        self, query: str, session: SessionMetadata, limit: int = 10
    ) -> list[LLMMessage]:
        """根据查询词搜索当前会话的历史消息。"""
        ...

    @abstractmethod
    async def add_messages(
        self, session: SessionMetadata, messages: list[LLMMessage]
    ) -> None:
        """向当前会话追加消息。"""
        ...

    @abstractmethod
    async def set_messages(
        self, session: SessionMetadata, messages: list[LLMMessage]
    ) -> None:
        """重置并设置当前会话的消息列表。"""
        ...

    @abstractmethod
    async def clear(self, session: SessionMetadata) -> None:
        """清空当前会话的历史消息。"""
        ...

    @abstractmethod
    async def clear_by_query(self, query: ScopeSelector) -> None:
        """根据条件领域查询对象清理对话历史。"""
        ...


class BaseSlotContext(ABC):
    """中期记忆槽持久化接口"""

    @abstractmethod
    async def get_slot(self, session: SessionMetadata, label: str) -> MemorySlot | None:
        """获取指定会话下特定标签的记忆槽。"""
        ...

    @abstractmethod
    async def set_slot(self, session: SessionMetadata, slot: MemorySlot) -> None:
        """设置或更新指定会话下的记忆槽。"""
        ...

    @abstractmethod
    async def delete_slot(
        self, session: SessionMetadata, label: str, scope: str
    ) -> None:
        """删除指定会话下特定标签和作用域的记忆槽。"""
        ...

    @abstractmethod
    async def list_pinned_slots(self, session: SessionMetadata) -> list[MemorySlot]:
        """列出当前会话所有固定的记忆槽。"""
        ...

    @abstractmethod
    async def list_all_slots(self, session: SessionMetadata) -> list[MemorySlot]:
        """列出当前会话的所有记忆槽（包括未置顶的）。"""
        ...

    @abstractmethod
    async def clear_by_query(self, query: ScopeSelector) -> None:
        """根据条件领域查询对象清理记忆槽。"""
        ...


class BaseMemoryReducer(ABC):
    """记忆压缩器基类"""

    @abstractmethod
    async def reduce(
        self,
        messages: list[LLMMessage],
        current_tokens: int,
        model_name: str,
        base_overhead: int = 0,
    ) -> tuple[list[LLMMessage], bool, int]:
        """对消息列表进行压缩处理。"""
        ...


class BaseMemoryIngestionMiddleware(ABC):
    """记忆入库中间件基类，在写入数据库前拦截并修改/清洗消息"""

    @abstractmethod
    async def process(
        self, messages: Sequence[AgentMessage], context: RunContext
    ) -> list[AgentMessage]: ...
