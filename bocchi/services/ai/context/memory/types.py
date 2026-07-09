from collections.abc import Awaitable, Callable
import time

from pydantic import BaseModel, ConfigDict, Field

from bocchi.services.ai.utils.scope import ScopeBuilder, ScopeSelector

AutoRecallPolicy = bool | Callable[[str, "SessionMetadata"], Awaitable[bool] | bool]
"""长期记忆的自动召回策略"""


class MemorySlot(BaseModel):
    """可编辑的持久化记忆槽 (Mid-Term Memory)"""

    label: str = Field(...)
    """槽位唯一标签标识 (如 persona, preferences)"""
    content: str = Field(default="")
    """槽位存储的具体文本内容"""
    size_limit: int = Field(default=2000)
    """槽位内容的最大字符数限制"""
    pinned: bool = Field(default=True)
    """是否固定注入到大模型的每次系统提示词中"""
    scope: str = Field(...)
    """作用域：表示隔离的路径前缀 (scope_prefix)"""
    description: str = Field(default="")
    """该记忆槽的用途说明，便于大模型理解"""
    created_at: float = Field(default_factory=time.time)
    """创建时间戳"""
    updated_at: float = Field(default_factory=time.time)
    """最近更新时间戳"""


class Isolation:
    """预设策略工厂，提供友好的隔离级别声明式 API"""

    @staticmethod
    def _base() -> ScopeBuilder:
        """获取底座通用隔离级别（包含Bot、平台、命名空间、智能体）。"""
        return ScopeBuilder().bot().platform().namespace().agent()

    @classmethod
    def GROUP_SHARED(cls) -> ScopeBuilder:
        """群组共享隔离：同群内共享金库与记忆。"""
        return cls._base().group()

    @classmethod
    def USER_GLOBAL(cls) -> ScopeBuilder:
        """用户全局隔离：跨群、跨插件共享用户记忆。"""
        return cls._base().user()

    @classmethod
    def GROUP_USER(cls) -> ScopeBuilder:
        """群组用户隔离：单群内单用户独立隔离。"""
        return cls._base().group().user()

    @classmethod
    def AGENT_USER(cls) -> ScopeBuilder:
        """智能体用户隔离：单智能体单用户物理隔离。"""
        return cls.GROUP_USER()


class SessionMetadata(BaseModel):
    """结构化会话元数据"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = Field(...)
    """核心会话标识符。"""
    selector: ScopeSelector = Field(default_factory=ScopeSelector)
    """统一的作用域与实体资源选择器。"""
    isolation_level: ScopeBuilder | None = Field(default=None)
    """生成此会话时的隔离级别。"""
    scope_prefix: str = Field(default="/")
    """基于隔离级别生成的路径作用域，用于长期记忆 (RAG) 的向量检索前缀过滤。"""
    accessible_scopes: list[str] = Field(default_factory=lambda: ["/"])
    """
    当前会话有权访问的作用域列表，用于 Slice 联合检索。
    """
    scope_name_mapping: dict[str, str] = Field(default_factory=dict)
    """物理路径到语义化名称的逆向映射字典，供大模型友好阅读"""

    @property
    def platform(self) -> str | None:
        return self.selector.platform

    @property
    def group_id(self) -> str | None:
        return self.selector.group_id

    @property
    def user_id(self) -> str | None:
        return self.selector.user_id

    @property
    def namespace(self) -> str | None:
        return self.selector.namespace

    @property
    def agent_name(self) -> str | None:
        return self.selector.agent_name

    def __str__(self) -> str:
        return self.session_id
