"""
LLM 服务模块 - 公共 API 入口

提供统一的 AI 服务调用接口、核心数据契约和配置工具。
"""

from bocchi.services.ai.core.exceptions import LLMException
from bocchi.services.ai.core.messages import (
    AudioResponse,
    ChatResponse,
    LLMContentPart,
    LLMMessage,
)
from bocchi.services.ai.core.options import (
    TTSConfig,
)

from .api import (
    chat,
    create_image,
    create_speech,
    embed,
    generate,
    generate_structured,
    rerank,
)
from .builder import (
    IntentBuilder,
)
from .manager import get_default_model

__all__ = [
    "AudioResponse",
    "ChatResponse",
    "IntentBuilder",
    "LLMContentPart",
    "LLMException",
    "LLMMessage",
    "TTSConfig",
    "chat",
    "create_image",
    "create_speech",
    "embed",
    "generate",
    "generate_structured",
    "get_default_model",
    "rerank",
]
