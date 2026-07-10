"""
标准消息实体 - 依赖 parts.py
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
import time
from typing import Annotated, Any, Generic, Literal, cast
from typing_extensions import Self, TypeVar

from pydantic import BaseModel, Field

from bocchi.utils.pydantic_compat import model_copy, model_dump, model_validator

from .parts import (
    BaseContentPart,
    FilePart,
    ImagePart,
    LLMContentPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

RoleT = TypeVar("RoleT", default=str, covariant=True)
"""泛型：消息参与者角色类型变量"""

ContentT = TypeVar("ContentT", default=LLMContentPart, covariant=True)
"""泛型：多模态片段数组的元素内容类型变量"""


class LLMMessage(BaseModel, Generic[RoleT, ContentT]):
    """
    LLM 消息基类与门面工厂。
    提供统一的元数据访问、魔法加法重载以及极简实例化方法。
    """

    role: RoleT
    """消息参与者角色 (如 user, assistant, system, tool)"""
    content: list[ContentT] = Field(default_factory=list)
    """容纳实际数据的多模态片段数组"""
    created_at: float = Field(default_factory=time.time)
    """消息最初被构建的 Unix 时间戳"""
    metadata: dict[str, Any] | None = Field(default=None)
    """自由存取字典，供系统内穿透传递额外状态数据"""

    @property
    def tool_calls(self) -> list[ToolCallPart]:
        """获取当前消息中包含的所有工具调用请求片段"""
        return [p for p in self.content if isinstance(p, ToolCallPart)]

    @property
    def tool_returns(self) -> list[ToolReturnPart]:
        """获取当前消息中包含的所有工具执行结果片段"""
        return [p for p in self.content if isinstance(p, ToolReturnPart)]

    @model_validator(mode="before")
    @classmethod
    def _normalize_content(cls, data: Any) -> Any:
        """核心拦截：外部传入 str 时自动转为 Part，保持内部类型绝对纯净"""
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, str):
                data["content"] = (
                    [{"type": "text", "text": content}] if content.strip() else []
                )
            elif content is None:
                data["content"] = []
            elif isinstance(content, list):
                new_content = []
                for item in content:
                    if isinstance(item, str):
                        new_content.append({"type": "text", "text": item})
                    else:
                        new_content.append(item)
                data["content"] = new_content
            elif not isinstance(content, list):
                import json

                try:
                    text_val = json.dumps(content, ensure_ascii=False)
                except Exception:
                    text_val = str(content)
                data["content"] = [{"type": "text", "text": text_val}]
        return data

    def __add__(self, other: str | LLMContentPart | "LLMMessage") -> Self:
        """极简语法糖：支持通过加号拼接文本或多模态片段。
        示例: msg = LLMMessage.user("查看图片：") + ImagePart(url="...")
        """
        new_msg = cast(Self, model_copy(self, deep=True))
        if isinstance(other, str):
            new_msg.content.append(cast(Any, TextPart(text=other)))
        elif isinstance(other, BaseContentPart):
            new_msg.content.append(cast(Any, other))
        elif isinstance(other, LLMMessage):
            new_msg.content.extend(cast(Any, other.content))
        return new_msg

    @property
    def extract_text(self) -> str:
        """便捷属性：提取当前消息中所有的纯文本"""
        return "".join(p.text for p in self.content if isinstance(p, TextPart))

    @property
    def source(self) -> str | None:
        """获取消息的来源标识 (存取于 metadata 中)"""
        return self.metadata.get("source") if self.metadata else None

    @source.setter
    def source(self, value: str | None):
        """设置消息的来源标识"""
        if self.metadata is None:
            self.metadata = {}
        self.metadata["source"] = value

    @property
    def source_name(self) -> str | None:
        """获取消息来源的具体名称 (例如真实用户的昵称)"""
        return self.metadata.get("source_name") if self.metadata else None

    @source_name.setter
    def source_name(self, value: str | None):
        """设置消息来源的具体名称"""
        if self.metadata is None:
            self.metadata = {}
        self.metadata["source_name"] = value

    @property
    def scope(self) -> str | None:
        """获取该消息所绑定的作用域或会话ID"""
        return self.metadata.get("scope") if self.metadata else None

    @scope.setter
    def scope(self, value: str | None):
        """设置该消息的作用域"""
        if self.metadata is None:
            self.metadata = {}
        self.metadata["scope"] = value

    @property
    def thought_signature(self) -> str | None:
        """获取连续对话中用于保持思考一致性的加密签名 (Gemini 专属)"""
        return self.metadata.get("thought_signature") if self.metadata else None

    @thought_signature.setter
    def thought_signature(self, value: str | None):
        """设置思考加密签名"""
        if self.metadata is None:
            self.metadata = {}
        self.metadata["thought_signature"] = value

    @property
    def token_cost(self) -> int | None:
        """获取该消息自身消耗的预估或真实 Token 数"""
        return self.metadata.get("token_cost") if self.metadata else None

    @token_cost.setter
    def token_cost(self, value: int | None):
        """设置 Token 消耗数"""
        if self.metadata is None:
            self.metadata = {}
        self.metadata["token_cost"] = value

    @classmethod
    def user(
        cls,
        content: str | Sequence[Any],
        source: str | None = None,
        source_name: str | None = None,
        scope: str | None = None,
    ) -> "UserMessage":
        """
        工厂方法：创建一条 User (用户) 角色的消息。

        参数:
            content: 消息内容，支持纯字符串或多模态片段数组。
            source: 可选，消息来源标识。
            source_name: 可选，消息来源的可读名称。
            scope: 可选，消息关联的会话作用域。
        """
        if isinstance(content, str):
            content = [TextPart(text=content)] if content.strip() else []
        elif not isinstance(content, list):
            content = list(content)
        msg = UserMessage(content=cast(Any, content))
        msg.source = source
        msg.source_name = source_name
        msg.scope = scope
        return msg

    @classmethod
    def assistant_tool_calls(
        cls,
        tool_calls: list[ToolCallPart],
        content: str | Sequence[Any] = "",
        scope: str | None = None,
    ) -> "AssistantMessage":
        """
        工厂方法：创建一条包含工具调用请求的 Assistant (助手) 角色消息。

        参数:
            tool_calls: 大模型发出的工具调用片段列表。
            content: 伴随工具调用的其他文本或思维过程。
            scope: 可选，消息关联的会话作用域。
        """
        if isinstance(content, str):
            _content: list[Any] = [TextPart(text=content)] if content else []
        else:
            _content = list(content)
        _content.extend(tool_calls)
        msg = AssistantMessage(content=cast(Any, _content))
        msg.scope = scope
        return msg

    @classmethod
    def assistant_text_response(
        cls,
        content: str | Sequence[Any],
        scope: str | None = None,
    ) -> "AssistantMessage":
        """
        工厂方法：创建一条仅包含普通文本/思维过程的 Assistant (助手) 角色消息。

        参数:
            content: 大模型生成的文本回复内容。
            scope: 可选，消息关联的会话作用域。
        """
        if isinstance(content, str):
            content = [TextPart(text=content)] if content and content.strip() else []
        elif not isinstance(content, list):
            content = list(content)
        msg = AssistantMessage(content=cast(Any, content))
        msg.scope = scope
        return msg

    def add_text(self, text: str) -> Self:
        """链式添加文本内容"""
        self.content.append(cast(Any, TextPart(text=text)))
        return self

    def add_image_url(self, url: str) -> Self:
        """链式添加网络图片"""
        self.content.append(cast(Any, ImagePart(url=url)))
        return self

    def add_image_base64(self, b64_data: str, mime_type: str = "image/png") -> Self:
        """链式添加 Base64 图片"""
        self.content.append(
            cast(Any, ImagePart(raw=base64.b64decode(b64_data), mime_type=mime_type))
        )
        return self

    def add_file_url(self, url: str, mime_type: str | None = None) -> Self:
        """链式添加文件链接"""
        self.content.append(cast(Any, FilePart(url=url, mime_type=mime_type)))
        return self

    @classmethod
    def tool_response(
        cls,
        tool_call_id: str,
        function_name: str,
        result: Any,
        scope: str | None = None,
    ) -> "ToolMessage":
        """
        工厂方法：创建一条 Tool (工具) 角色消息，用于承载工具执行完毕后的返回结果。

        参数:
            tool_call_id: 对应的大模型发出调用请求时的 ID。
            function_name: 执行的工具名称。
            result: 工具执行的结果负载 (会被自动 JSON 序列化)。
            scope: 可选，消息关联的会话作用域。
        """
        _content = [
            ToolReturnPart(
                tool_call_id=tool_call_id, tool_name=function_name, output=result
            )
        ]
        msg = ToolMessage(content=cast(Any, _content))
        msg.scope = scope
        return msg

    @classmethod
    def system(
        cls,
        content: str | Sequence[Any],
        scope: str | None = None,
    ) -> "SystemMessage":
        """
        工厂方法：创建一条 System (系统) 角色的设定消息。

        参数:
            content: 系统的 Prompt 指令。
            scope: 可选，消息关联的会话作用域。
        """
        if isinstance(content, str):
            content = [TextPart(text=content)] if content.strip() else []
        elif not isinstance(content, list):
            content = list(content)
        msg = SystemMessage(content=cast(Any, content))
        msg.scope = scope
        return msg

    def to_storage_dict(self) -> dict[str, Any]:
        """数据库瘦身存储，仅保留核心字段"""
        return model_dump(
            self,
            exclude_none=True,
            include={
                "role",
                "content",
                "metadata",
            },
        )


class SystemMessage(LLMMessage[Literal["system"], TextPart]):
    """系统消息：通常用于在对话开头向模型提供系统级指令 (System Prompt)、
    角色设定或背景上下文。"""

    role: Literal["system"] = "system"
    content: list[Annotated[TextPart, Field(discriminator="type")]] = Field(
        default_factory=list
    )


class UserMessage(LLMMessage[Literal["user"], LLMContentPart]):
    """用户消息：代表来自最终用户或外部触发源的输入，支持包含文本、图片、文件等多模态数据。"""

    role: Literal["user"] = "user"
    content: list[LLMContentPart] = Field(default_factory=list)


class AssistantMessage(LLMMessage[Literal["assistant"], LLMContentPart]):
    """助手消息：代表大模型 (AI) 生成的回复。
    可能包含纯文本、思维链过程或工具调用请求。"""

    role: Literal["assistant"] = "assistant"
    content: list[LLMContentPart] = Field(default_factory=list)


class ToolMessage(LLMMessage[Literal["tool"], LLMContentPart]):
    """工具消息：用于承载由用户端执行工具后，将结果返回给大模型的消息容器。"""

    role: Literal["tool"] = "tool"
    content: list[LLMContentPart] = Field(default_factory=list)

    def model_post_init(self, context: Any, /) -> None:
        """验证消息的有效性"""
        if not self.tool_returns:
            raise ValueError("工具角色的消息必须包含 ToolReturnPart")


__all__ = [
    "AssistantMessage",
    "ContentT",
    "LLMMessage",
    "RoleT",
    "SystemMessage",
    "ToolMessage",
    "UserMessage",
]
