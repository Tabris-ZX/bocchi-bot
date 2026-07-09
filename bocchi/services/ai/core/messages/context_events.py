from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .models import LLMMessage


class AgentEvent(BaseModel):
    """
    业务事件抽象基类/协议。
    支持作为一种特殊的消息，直接被混入到大模型的上下文(记忆)中。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")  # type: ignore

    def to_llm_message(
        self, context: Any | None = None
    ) -> LLMMessage | list[LLMMessage] | str | None:
        """
        将业务事件渲染为大模型能看懂的 API 原生消息。
        子类必须重写此方法。
        返回 None 代表此事件对大模型不可见(例如：纯后台打点或审计日志)。
        如果返回 str，系统将默认包装为 SystemMessage 发送给大模型。
        """
        return None


class TaskLifecycleEvent(AgentEvent):
    """内置业务事件：任务状态打点追踪"""

    task_name: str
    """任务名称"""
    action: Literal["start", "complete", "fail"]
    """任务状态动作，支持 "start"（开始）、"complete"（完成）、"fail"（失败）"""
    error_msg: str | None = None
    """任务执行失败时的具体错误描述，可选"""

    def to_llm_message(self, context: Any | None = None) -> str | None:
        if self.action == "start":
            return f"[任务生命周期] 开始执行任务：{self.task_name}"
        elif self.action == "complete":
            return f"[任务生命周期] 任务已完美达成：{self.task_name}"
        elif self.action == "fail":
            return (
                f"[任务生命周期] 任务执行失败：{self.task_name}，原因：{self.error_msg}"
            )
        return None


class HandoffEvent(AgentEvent):
    """内置业务事件：控制权移交记录"""

    target: str
    """目标接收节点或 Agent 的名称"""
    reason: str
    """移交控制权的具体原因说明"""
    context_data: Any = None
    """移交时附带的上下文数据，默认为 None"""

    def to_llm_message(self, context: Any | None = None) -> str | None:
        return (
            f"[控制权移交] 任务及会话控制权已被系统转移至节点 "
            f"'{self.target}'。移交原因：{self.reason}"
        )


__all__ = [
    "AgentEvent",
    "HandoffEvent",
    "TaskLifecycleEvent",
]
