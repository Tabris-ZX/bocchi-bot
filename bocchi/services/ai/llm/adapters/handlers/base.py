from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from typing import Any

import httpx

from bocchi.services.ai.core.messages import (
    AudioResponse,
    ChatRequest,
    EmbeddingRequest,
    ImageRequest,
    LLMMessage,
    RerankRequest,
    RerankResult,
    SpeechRequest,
)
from bocchi.services.ai.core.models import (
    ModelCapabilities,
    ModelDetail,
    ModelIdentity,
    ToolDefinition,
)
from bocchi.services.ai.core.options import (
    GenerationConfig,
)
from bocchi.services.ai.llm.adapters.base import BaseAdapter, RequestData, ResponseData


class ConfigMapper(ABC):
    @abstractmethod
    def map_config(
        self,
        config: GenerationConfig,
        model_detail: ModelDetail | None = None,
        capabilities: ModelCapabilities | None = None,
    ) -> dict[str, Any]:
        """将通用生成配置转换为特定 API 的参数字典"""
        ...


class MessageConverter(ABC):
    @abstractmethod
    async def convert_messages_async(
        self, messages: list[LLMMessage]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """将通用消息列表异步转换为特定 API 的消息格式"""
        ...


class ToolSerializer(ABC):
    def serialize_tools(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]] | None:
        """将通用工具定义转换为特定 API 的工具格式 (模板方法)"""
        if not tools:
            return None

        serialized_tools = []
        for tool in tools:
            raw_schema = tool.parameters.copy() if tool.parameters else {}
            sanitized_schema = self.sanitize_schema(raw_schema)
            tool_payload = self.format_tool_payload(
                tool_name=tool.name,
                tool_description=tool.description or "",
                sanitized_schema=sanitized_schema,
            )
            serialized_tools.append(tool_payload)
        return serialized_tools

    @abstractmethod
    def format_tool_payload(
        self, tool_name: str, tool_description: str, sanitized_schema: dict[str, Any]
    ) -> dict[str, Any]:
        """由子类实现：格式化单一工具的 Payload"""
        ...

    @abstractmethod
    def sanitize_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """对 JSON Schema 进行特定 API 的清洗和格式化"""
        ...

    @abstractmethod
    def serialize_server_tools(
        self, tools: list[Any], capabilities: ModelCapabilities
    ) -> list[dict[str, Any]]:
        """将系统内置的原生云端工具转译为底层 API 载荷（执行双重能力校验）"""
        ...


class ResponseParser(ABC):
    @abstractmethod
    def parse(self, response_json: dict[str, Any]) -> ResponseData:
        """将特定 API 的响应解析为通用响应数据"""
        ...


class BaseTextHandler(ABC):
    """
    文本对话生成处理器接口。
    负责将波奇的通用消息与工具列表转换为底层 API 的请求格式，并解析响应。
    """

    async def _resolve_and_split_tools(
        self, tools: list[Any] | None
    ) -> tuple[list[Any], list[Any], list[Any]]:
        """
        统一的工具解析逻辑：分离客户端工具与服务端内置工具，并发获取 Schema。
        返回: (tool_defs, client_executables, server_tools)
        """
        client_executables, server_tools, tool_defs = [], [], []
        if tools:
            raw_tools = list(tools.values()) if isinstance(tools, dict) else tools
            for tool in raw_tools:
                if getattr(tool, "execution_side", "client") == "server":
                    server_tools.append(tool)
                elif hasattr(tool, "get_definition"):
                    client_executables.append(tool)
            if definition_tasks := [t.get_definition() for t in client_executables]:
                tool_defs = [td for td in await asyncio.gather(*definition_tasks) if td]
        return tool_defs, client_executables, server_tools

    @abstractmethod
    async def prepare_text_request(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        api_key: str,
        request: ChatRequest,
    ) -> RequestData: ...

    @abstractmethod
    def parse_text_response(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        response_json: dict[str, Any],
        is_advanced: bool = False,
    ) -> ResponseData: ...


class BaseEmbeddingHandler(ABC):
    """
    文本嵌入向量处理器接口。
    """

    @abstractmethod
    async def prepare_embedding_request(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        api_key: str,
        request: EmbeddingRequest,
    ) -> RequestData: ...

    @abstractmethod
    def parse_embedding_response(
        self, adapter: BaseAdapter, response_json: dict[str, Any]
    ) -> list[list[float]]: ...


class BaseImageHandler(ABC):
    """
    图像生成/编辑处理器接口。
    """

    @abstractmethod
    def prepare_image_request(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        api_key: str,
        request: ImageRequest,
    ) -> RequestData: ...

    @abstractmethod
    def parse_image_response(
        self, adapter: BaseAdapter, response_json: dict[str, Any]
    ) -> ResponseData: ...


class BaseRerankHandler(ABC):
    """
    文本重排处理器接口。
    """

    @abstractmethod
    def prepare_rerank_request(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        api_key: str,
        request: RerankRequest,
    ) -> RequestData: ...

    @abstractmethod
    def parse_rerank_response(
        self, adapter: BaseAdapter, response_json: dict[str, Any]
    ) -> list[RerankResult]: ...


class BaseAudioHandler(ABC):
    """
    文本转语音 (TTS) 处理器接口。
    """

    @abstractmethod
    def prepare_speech_request(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        api_key: str,
        request: SpeechRequest,
    ) -> RequestData: ...

    @abstractmethod
    async def parse_speech_response(
        self,
        adapter: BaseAdapter,
        identity: ModelIdentity,
        raw_response: httpx.Response,
    ) -> AudioResponse: ...
