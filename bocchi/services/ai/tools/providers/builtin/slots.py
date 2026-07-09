import asyncio
from contextlib import asynccontextmanager
import time
from typing import Any, Literal

from pydantic import Field, create_model

from bocchi.services.ai.context.memory.manager import memory_manager
from bocchi.services.ai.context.memory.models import MemoryConfig
from bocchi.services.ai.context.memory.types import (
    MemorySlot,
    SessionMetadata,
)
from bocchi.services.ai.run.context import RunContext
from bocchi.services.ai.tools.core.decorators import tool
from bocchi.services.ai.tools.core.tool import BaseTool
from bocchi.services.ai.tools.core.toolkit import BaseToolkit
from bocchi.services.ai.tools.models import ToolOptions, ToolResult

_SLOT_LOCKS: dict[str, asyncio.Lock] = {}
_GLOBAL_LOCK = asyncio.Lock()


@asynccontextmanager
async def _slot_lock(session_id: str, label: str):
    key = f"{session_id}:{label}"
    async with _GLOBAL_LOCK:
        if key not in _SLOT_LOCKS:
            _SLOT_LOCKS[key] = asyncio.Lock()
        lock = _SLOT_LOCKS[key]
    async with lock:
        yield


class MemorySlotToolkit(BaseToolkit):
    """
    中期记忆槽工具箱。
    向大模型开放直接编辑上下文 XML 节点的能力。
    """

    default_prefix = ""

    class Config:
        """声明式配置：该工具箱下的所有工具默认静默"""

        shared_options = ToolOptions(silent=True)

    default_instructions = """\
## 📋 状态与规则面板 (Memory Slots / 中期记忆)
该系统是你的「桌面便利贴」或「共享黑板」，用于保存你当前需要随时查阅的核心状态与全局规范。

### 💡 核心机制
- 被保存在记忆槽中的内容（如果已置顶），会在每次对话时**直接注入到你的上下文提示词中**，你无需任何搜索即可看见。
- 槽位容量极其有限，仅用于维持当前最新的运行状态。

### 📝 何时使用记忆槽？
- **维护全局规则**：例如设定"用户整体偏好"、"沟通口吻"、"全局指导原则"等需要时刻遵守的规范（使用 `update_slot`）。
- **追踪当前进度**：例如记录"待办事项清单"、"当前任务进度"、"上下文摘要"（使用 `append_slot` 列表或 `update_slot` 覆盖）。

### ⚙️ 操作规范
1. **探索可用面板**：接手新任务时，可使用 `list_slots` 宏观查看当前存在哪些状态面板。
2. **保持精简**：槽位有严格的字符数限制。当内容过长时，请主动将其归档到长期记忆后，重新提炼并覆盖槽位，或直接调用 `delete_slot` 删除不再需要的槽位。\
"""  # noqa: E501

    def __init__(
        self,
        memory_config: MemoryConfig | None = None,
        namespace: str | None = None,
        **kwargs: Any,
    ):
        """
        初始化中期记忆槽工具箱。

        参数：
            memory_config: 记忆系统的全局配置对象，为空则使用全局默认。
            namespace: 当前隔离环境的命名空间。
            kwargs: 其他透传给 BaseToolkit 的参数。
        """
        super().__init__(**kwargs)
        self.memory_config = memory_config
        self._namespace = namespace

    def _get_runtime_meta_and_ctx(
        self, context: RunContext, scope_name: str | None = None
    ) -> tuple[Any, SessionMetadata]:
        ns = self._namespace or getattr(context.session, "namespace", "global")
        slot_ctx = memory_manager.get_slot_context(self.memory_config, namespace=ns)

        scope_builder = None
        if (
            self.memory_config
            and self.memory_config.slots
            and self.memory_config.slots.scopes
        ):
            scopes_dict = self.memory_config.slots.scopes
            if not scope_name:
                scope_builder = next(iter(scopes_dict.values()))
            else:
                scope_builder = scopes_dict.get(scope_name)

        if not scope_builder:
            scope_builder = getattr(self.memory_config, "base_isolation", None)
            if not scope_builder:
                from bocchi.services.ai.context.memory.types import Isolation

                scope_builder = Isolation.AGENT_USER()

        selector = scope_builder.resolve(
            deps=context.deps,
            prefix="",
            default_namespace=ns,
            default_agent=context.run.agent_name,
        )
        parts = selector.get_scope_parts()
        all_scopes = {"/"}
        current_path = ""
        for part in parts:
            current_path += f"/{part}"
            all_scopes.add(current_path)
        accessible_scopes = list(all_scopes)
        accessible_scopes.sort(key=lambda x: len(x.split("/")))

        scope_name_mapping = {}
        if (
            self.memory_config
            and self.memory_config.slots
            and self.memory_config.slots.scopes
        ):
            for name, builder in self.memory_config.slots.scopes.items():
                sel = builder.resolve(
                    deps=context.deps,
                    prefix="",
                    default_namespace=ns,
                    default_agent=context.run.agent_name,
                )
                scope_name_mapping[sel.scope_prefix] = name

        session_meta = SessionMetadata(
            session_id=context.session_id or "default_session",
            selector=selector,
            scope_prefix=selector.scope_prefix,
            accessible_scopes=accessible_scopes,
            scope_name_mapping=scope_name_mapping,
        )
        return slot_ctx, session_meta

    async def get_tools(self, context: RunContext | None = None) -> dict[str, BaseTool]:
        tools = await super().get_tools(context)

        if (
            not self.memory_config
            or not self.memory_config.slots
            or not self.memory_config.slots.enable
        ):
            return tools

        scopes_dict = self.memory_config.slots.scopes
        if not scopes_dict:
            return tools
        scope_keys = tuple(scopes_dict.keys())

        if len(scope_keys) > 1:
            ScopeType = Literal[scope_keys]

            UpdateArgs = create_model(
                "UpdateSlotArgs",
                label=(str, Field(..., description="槽位标签名称")),
                content=(str, Field(..., description="槽位内容(全量覆写)")),
                description=(str, Field(default="", description="槽位的简要说明")),
                scope=(
                    ScopeType,
                    Field(..., description="选择记忆存储的隔离分区"),
                ),
            )

            AppendArgs = create_model(
                "AppendSlotArgs",
                label=(str, Field(..., description="槽位标签名称")),
                text=(str, Field(..., description="要追加的文本内容")),
                scope=(
                    ScopeType,
                    Field(..., description="选择记忆存储的隔离分区"),
                ),
            )

            ReadArgs = create_model(
                "ReadSlotArgs",
                label=(str, Field(..., description="槽位标签名称")),
                scope=(
                    ScopeType,
                    Field(..., description="选择记忆存储的隔离分区"),
                ),
            )

            DeleteArgs = create_model(
                "DeleteSlotArgs",
                label=(str, Field(..., description="槽位标签名称")),
                scope=(
                    ScopeType,
                    Field(..., description="选择记忆存储的隔离分区"),
                ),
            )

            ListArgs = create_model(
                "ListSlotsArgs",
                scope=(
                    ScopeType,
                    Field(..., description="选择记忆存储的隔离分区"),
                ),
            )

            for t_name, t in tools.items():
                if t_name.endswith("update_slot"):
                    t.args_schema = UpdateArgs
                elif t_name.endswith("append_slot"):
                    t.args_schema = AppendArgs
                elif t_name.endswith("read_slot"):
                    t.args_schema = ReadArgs
                elif t_name.endswith("delete_slot"):
                    t.args_schema = DeleteArgs
                elif t_name.endswith("list_slots"):
                    t.args_schema = ListArgs

        return tools

    @tool(
        description="列出当前所有可用的记忆槽（包括未置顶显示的槽位），方便你了解有哪些信息可供读取或更新。"
    )
    async def list_slots(self, context: RunContext, **kwargs) -> ToolResult:
        scope_name = kwargs.get("scope")
        slot_ctx, meta = self._get_runtime_meta_and_ctx(context, scope_name)
        if not slot_ctx:
            return ToolResult(output="错误：未配置记忆槽后端").as_error()
        slots = await slot_ctx.list_all_slots(meta)
        if not slots:
            return ToolResult(output="当前没有任何记忆槽。")
        res = ["已创建的记忆槽列表："]

        show_scope = False
        if (
            self.memory_config
            and self.memory_config.slots
            and self.memory_config.slots.scopes
            and len(self.memory_config.slots.scopes) > 1
        ):
            show_scope = True

        for s in slots:
            pin_str = "置顶" if s.pinned else "隐藏"
            if show_scope:
                semantic_name = meta.scope_name_mapping.get(s.scope, "未知")
                res.append(
                    f"- [{s.label}] (分区: "
                    f"{semantic_name}, {pin_str}) - {s.description}"
                )
            else:
                res.append(f"- [{s.label}] ({pin_str}) - {s.description}")
        return ToolResult(output="\n".join(res))

    @tool(description="读取某个尚未展示在上下文中的记忆槽完整内容。")
    async def read_slot(self, label: str, context: RunContext, **kwargs) -> ToolResult:
        scope_name = kwargs.get("scope")
        slot_ctx, meta = self._get_runtime_meta_and_ctx(context, scope_name)
        if not slot_ctx:
            return ToolResult(output="错误：未配置记忆槽后端").as_error()
        slot = await slot_ctx.get_slot(meta, label)
        if not slot:
            return ToolResult(output=f"未找到标签为 '{label}' 的槽位。").as_error()
        return ToolResult(output=f"[{label}] 内容:\n{slot.content}")

    @tool(description=("更新或新建记忆槽的内容（全量覆写）。"))
    async def update_slot(
        self,
        label: str,
        content: str,
        context: RunContext,
        description: str = "",
        **kwargs,
    ) -> ToolResult:
        scope_name = kwargs.get("scope")
        slot_ctx, meta = self._get_runtime_meta_and_ctx(context, scope_name)
        if not slot_ctx:
            return ToolResult(output="错误：未配置记忆槽后端").as_error()

        target_sid = meta.scope_prefix
        async with _slot_lock(target_sid, label):
            slot = await slot_ctx.get_slot(meta, label)
            if not slot:
                slot = MemorySlot(
                    label=label,
                    content=content,
                    scope=meta.scope_prefix,
                    description=description,
                )
            else:
                slot.content = content
                slot.scope = meta.scope_prefix
                if description:
                    slot.description = description
                slot.updated_at = time.time()

            if len(content) > slot.size_limit:
                return ToolResult(
                    output=(
                        f"错误：内容长度超过限制 ({len(content)} > {slot.size_limit})。"
                    )
                ).as_error()

            await slot_ctx.set_slot(meta, slot)
            return ToolResult(output=f"已成功将 '{label}' 更新至记忆槽中。")

    @tool(description="在指定记忆槽的末尾追加文本（例如追加待办事项清单）。")
    async def append_slot(
        self, label: str, text: str, context: RunContext, **kwargs
    ) -> ToolResult:
        scope_name = kwargs.get("scope")
        slot_ctx, meta = self._get_runtime_meta_and_ctx(context, scope_name)
        if not slot_ctx:
            return ToolResult(output="错误：未配置记忆槽后端").as_error()

        slot = await slot_ctx.get_slot(meta, label)
        if not slot:
            return ToolResult(
                output=(
                    f"错误：标签为 '{label}' 的槽位不存在，请先使用 update_slot 创建。"
                )
            ).as_error()

        target_sid = meta.scope_prefix

        async with _slot_lock(target_sid, label):
            slot = await slot_ctx.get_slot(meta, label)
            if not slot:
                return ToolResult(
                    output="错误：并发写入异常，槽位已被删除。"
                ).as_error()

            sep = "\n" if slot.content and not slot.content.endswith("\n") else ""
            new_content = f"{slot.content}{sep}{text}"

            if len(new_content) > slot.size_limit:
                return ToolResult(
                    output=(
                        "错误：追加后总长度超过限制 "
                        f"({len(new_content)} > {slot.size_limit})。"
                    )
                ).as_error()

            slot.content = new_content
            slot.updated_at = time.time()
            await slot_ctx.set_slot(meta, slot)

            return ToolResult(output=f"已成功追加至 '{label}'。")

    @tool(description="删除不再需要的记忆槽（全量删除）。")
    async def delete_slot(
        self, label: str, context: RunContext, **kwargs
    ) -> ToolResult:
        scope_name = kwargs.get("scope")
        slot_ctx, meta = self._get_runtime_meta_and_ctx(context, scope_name)
        if not slot_ctx:
            return ToolResult(output="错误：未配置记忆槽后端").as_error()

        target_sid = meta.scope_prefix
        async with _slot_lock(target_sid, label):
            await slot_ctx.delete_slot(meta, label, meta.scope_prefix)

        return ToolResult(output=f"已成功删除槽位 '{label}'。")
