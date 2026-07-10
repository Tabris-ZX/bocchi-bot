"""
Gemini API 适配器
"""

from __future__ import annotations

from bocchi.services.ai.core.models import ModelIdentity
from bocchi.services.ai.core.options import GenerationConfig

from .base import BaseAdapter
from .handlers.gemini_handlers import (
    GeminiAudioHandler,
    GeminiEmbeddingHandler,
    GeminiImageHandler,
    GeminiTextHandler,
)


class GeminiAdapter(BaseAdapter):
    """Gemini API 适配器"""

    def __init__(self):
        """初始化 Gemini 适配器并挂载各模态处理器。"""
        super().__init__()
        self.text_handler = GeminiTextHandler()
        self.image_handler = GeminiImageHandler()
        self.embedding_handler = GeminiEmbeddingHandler()
        self.audio_handler = GeminiAudioHandler()

    @property
    def log_sanitization_context(self) -> str:
        """返回 Gemini 请求日志清洗上下文。"""
        return "gemini_request"

    @property
    def api_type(self) -> str:
        """适配器主类型标识。"""
        return "gemini"

    @property
    def supported_api_types(self) -> list[str]:
        """当前适配器支持的 API 类型列表。"""
        return ["gemini"]

    def get_base_headers(self, api_key: str) -> dict[str, str]:
        """获取基础请求头"""
        from bocchi.utils.user_agent import get_user_agent

        headers = get_user_agent()
        headers.update({"Content-Type": "application/json"})
        headers["x-goog-api-key"] = api_key

        return headers

    def _get_gemini_endpoint(
        self, identity: ModelIdentity, config: GenerationConfig | None = None
    ) -> str:
        """返回Gemini generateContent 端点"""
        return f"/v1beta/models/{identity.model_name}:generateContent"
