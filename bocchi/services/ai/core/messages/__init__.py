"""
消息与响应域类型定义 - 统一导出门面
"""

from nonebot.compat import PYDANTIC_V2

from .context_events import (
    AgentEvent,
    HandoffEvent,
    TaskLifecycleEvent,
)
from .models import (
    AssistantMessage,
    LLMMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from .parts import (
    AudioPart,
    BaseContentPart,
    EmbedBatch,
    EmbedPayload,
    FilePart,
    ImagePart,
    LLMContentPart,
    TextDeltaPart,
    TextPart,
    ThoughtDeltaPart,
    ThoughtPart,
    ToolCallDeltaPart,
    ToolCallPart,
    ToolReturnPart,
    VideoPart,
)
from .requests import (
    BaseRequest,
    ChatRequest,
    EmbeddingRequest,
    ImageRequest,
    RerankRequest,
    SpeechRequest,
)
from .responses import (
    AudioResponse,
    ChatResponse,
    EmbeddingResponse,
    ImageResponse,
    RerankResponse,
)
from .shared import (
    LLMCodeExecution,
    LLMGroundingAttribution,
    LLMGroundingMetadata,
    RerankDocument,
    RerankResult,
    UsageInfo,
)
from .types import (
    AgentMessage,
    AnyLLMMessage,
    AssistantContentUnion,
    ContentT,
    PromptInput,
    RoleT,
    SystemContentUnion,
    ToolContentUnion,
    UserContentUnion,
)

if PYDANTIC_V2:
    ChatResponse.model_rebuild()
    LLMMessage.model_rebuild()
    SystemMessage.model_rebuild()
    UserMessage.model_rebuild()
    AssistantMessage.model_rebuild()
    ToolMessage.model_rebuild()
    RerankResponse.model_rebuild()


__all__ = [
    "AgentEvent",
    "AgentMessage",
    "AnyLLMMessage",
    "AssistantContentUnion",
    "AssistantMessage",
    "AudioPart",
    "AudioResponse",
    "BaseContentPart",
    "BaseRequest",
    "ChatRequest",
    "ChatResponse",
    "ContentT",
    "EmbedBatch",
    "EmbedPayload",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "FilePart",
    "HandoffEvent",
    "ImagePart",
    "ImageRequest",
    "ImageResponse",
    "LLMCodeExecution",
    "LLMContentPart",
    "LLMGroundingAttribution",
    "LLMGroundingMetadata",
    "LLMMessage",
    "PromptInput",
    "RerankDocument",
    "RerankRequest",
    "RerankResponse",
    "RerankResult",
    "RoleT",
    "SpeechRequest",
    "SystemContentUnion",
    "SystemMessage",
    "TaskLifecycleEvent",
    "TextDeltaPart",
    "TextPart",
    "ThoughtDeltaPart",
    "ThoughtPart",
    "ToolCallDeltaPart",
    "ToolCallPart",
    "ToolContentUnion",
    "ToolMessage",
    "ToolReturnPart",
    "UsageInfo",
    "UserContentUnion",
    "UserMessage",
    "VideoPart",
]
