"""
LLM Token 动态预估与上下文管理模块
"""

from collections.abc import Sequence
import math
import re
from typing import Any

from bocchi.services.ai.core.messages import (
    AgentEvent,
    AgentMessage,
    AudioPart,
    FilePart,
    ImagePart,
    LLMMessage,
    TextPart,
    ThoughtPart,
    ToolCallPart,
    ToolMessage,
    ToolReturnPart,
    UsageInfo,
    VideoPart,
)


class TokenCounter:
    """
    Token 计数器
    基于确定性规则，摆脱外部库依赖，提供绝对稳定的 Token 消耗预估基线。
    """

    @staticmethod
    def _count_text(text: str) -> int:
        """基于字符类型近似计算纯文本的 Token 消耗量。"""
        if not text:
            return 0
        cjk_chars = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text))
        ascii_chars = len(text) - cjk_chars
        return math.ceil(cjk_chars * 1.2 + ascii_chars * 0.3)

    @staticmethod
    def _count_image(resolution_hint: str | None, model_name: str) -> int:
        """根据分辨率策略和模型厂商计算单张图片的 Token 消耗量。"""
        if "gemini" in model_name.lower():
            res = (resolution_hint or "").upper()
            if "ULTRA_HIGH" in res:
                return 6192
            if "HIGH" in res:
                return 3096
            if "LOW" in res:
                return 258
            return 1032
        return 765

    @classmethod
    def count_tools_schema(cls, obj: dict | list | str | Any) -> int:
        """递归计算 JSON Schema 结构在被大模型作为工具时的 Token 开销。"""
        if isinstance(obj, dict):
            cost = len(obj.keys()) * 12
            for k, v in obj.items():
                if k == "description" and isinstance(v, str):
                    cost += int(len(v) * 0.3)
                else:
                    cost += cls.count_tools_schema(v)
            return cost
        elif isinstance(obj, list):
            return sum(cls.count_tools_schema(item) for item in obj)
        return 0

    @classmethod
    def count_message(cls, msg: LLMMessage, model_name: str) -> int:
        """累加计算单条包含多模态片段和工具调用的消息 Token 总数。"""
        if msg.token_cost is not None:
            return msg.token_cost

        total_tokens = 4

        if isinstance(msg, ToolMessage):
            total_tokens += 40

        if isinstance(msg.content, str):
            total_tokens += cls._count_text(msg.content)
        elif isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, TextPart) and part.text:
                    total_tokens += cls._count_text(part.text)
                elif isinstance(part, ImagePart):
                    total_tokens += cls._count_image(
                        getattr(part, "media_resolution", None), model_name
                    )
                elif isinstance(part, VideoPart | AudioPart | FilePart):
                    total_tokens += 1032
                elif isinstance(part, ThoughtPart) and part.thought_text:
                    total_tokens += cls._count_text(part.thought_text)
                elif isinstance(part, ToolCallPart) and part.args:
                    total_tokens += cls._count_text(str(part.args))
                elif isinstance(part, ToolReturnPart) and part.output:
                    total_tokens += cls._count_text(str(part.output))

        msg.token_cost = total_tokens
        return total_tokens

    @classmethod
    def count_context(
        cls, messages: Sequence[AgentMessage], model_name: str, base_overhead: int = 0
    ) -> int:
        """计算整个对话历史上下文的 Token 总和。"""
        if not messages:
            return base_overhead

        total = base_overhead
        for msg in messages:
            if isinstance(msg, AgentEvent):
                try:
                    res = msg.to_llm_message(None)
                    if res is None:
                        continue
                    if isinstance(res, str):
                        total += cls.count_message(LLMMessage.system(res), model_name)
                    elif isinstance(res, list):
                        total += sum(cls.count_message(m, model_name) for m in res)
                    elif isinstance(res, LLMMessage):
                        total += cls.count_message(res, model_name)
                except Exception:
                    pass
            else:
                total += cls.count_message(msg, model_name)
        return total


token_counter = TokenCounter


def parse_usage_info(usage_info: dict | None) -> UsageInfo:
    """
    全协议统一遥测解析器 (Universal Telemetry Parser)
    兼容 OpenAI Standard、OpenAI Responses (v1/responses) 以及 Gemini (usageMetadata)。
    """
    if not usage_info or not isinstance(usage_info, dict):
        return UsageInfo()

    prompt = 0
    completion = 0
    total = 0
    cache_hit = 0
    cache_miss = 0
    reasoning = 0

    if "promptTokenCount" in usage_info or "candidatesTokenCount" in usage_info:
        prompt = usage_info.get("promptTokenCount", 0)
        completion = usage_info.get("candidatesTokenCount", 0)
        total = usage_info.get("totalTokenCount", 0)
        reasoning = usage_info.get("thoughtsTokenCount", 0)
        cache_hit = usage_info.get("cachedContentTokenCount", 0)

    elif "input_tokens" in usage_info or "output_tokens" in usage_info:
        prompt = usage_info.get("input_tokens", 0)
        completion = usage_info.get("output_tokens", 0)
        total = usage_info.get("total_tokens", 0)
        cache_hit = (usage_info.get("input_tokens_details") or {}).get(
            "cached_tokens", 0
        )
        reasoning = (usage_info.get("output_tokens_details") or {}).get(
            "reasoning_tokens", 0
        )

    else:
        prompt = usage_info.get("prompt_tokens", 0)
        completion = usage_info.get("completion_tokens", 0)
        total = usage_info.get("total_tokens", 0)

        cache_hit = usage_info.get("prompt_cache_hit_tokens") or (
            usage_info.get("prompt_tokens_details") or {}
        ).get("cached_tokens", 0)
        cache_miss = usage_info.get("prompt_cache_miss_tokens", 0)
        reasoning = (usage_info.get("completion_tokens_details") or {}).get(
            "reasoning_tokens", 0
        )

    if cache_miss == 0 and prompt > 0:
        cache_miss = max(0, prompt - cache_hit)

    return UsageInfo(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        prompt_cache_hit_tokens=cache_hit,
        prompt_cache_miss_tokens=cache_miss,
        reasoning_tokens=reasoning,
    )
