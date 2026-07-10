from typing import Protocol, runtime_checkable

from bocchi.services.ai.core.messages import (
    AudioResponse,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ImageRequest,
    ImageResponse,
    RerankRequest,
    RerankResponse,
    SpeechRequest,
)
from bocchi.services.ai.core.models import CancellationToken


@runtime_checkable
class SupportsChat(Protocol):
    """支持文本/多模态对话生成的协议"""

    async def generate_response(
        self,
        request: ChatRequest,
        cancellation_token: CancellationToken | None = None,
    ) -> ChatResponse:
        """生成文本或多模态对话的回复。"""
        ...


@runtime_checkable
class SupportsTextEmbedding(Protocol):
    """支持文本/多模态向量嵌入的协议"""

    async def generate_embeddings(
        self,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        """生成文本或多模态向量嵌入。"""
        ...


@runtime_checkable
class SupportsSpeechSynthesis(Protocol):
    """支持文本转语音(TTS)的协议"""

    async def generate_speech(
        self,
        request: SpeechRequest,
    ) -> AudioResponse:
        """将文本转换为语音（TTS）。"""
        ...


@runtime_checkable
class SupportsReranking(Protocol):
    """支持文档交叉注意力重排的协议"""

    async def rerank(
        self,
        request: RerankRequest,
    ) -> RerankResponse:
        """对候选文档进行交叉注意力重排。"""
        ...


@runtime_checkable
class SupportsImageGeneration(Protocol):
    """支持图像生成与编辑的协议"""

    async def generate_image(
        self,
        request: ImageRequest,
    ) -> ImageResponse:
        """根据请求生成或编辑图像。"""
        ...
