"""Bocchi/NoneBot LLM bridge used by the analysis pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import random
from typing import Any

from bocchi.services.ai import LLMMessage
from bocchi.services.ai.llm import generate

from ....utils.logger import logger
from ....utils.resilience import GlobalRateLimiter
from ...config.config_manager import ConfigManager
from .structured_output_schema import JSONObject, JSONValue


@dataclass
class LLMResponse:
    """Small compatibility view consumed by the original analyzers."""

    role: str = "assistant"
    completion_text: str = ""
    usage: Any = None
    raw_completion: Any = None


def _configured_model(
    config_manager: ConfigManager,
    provider_id_key: str | None,
    provider_id: str | None,
) -> str | None:
    if provider_id:
        return provider_id.strip() or None
    if provider_id_key:
        getter = getattr(config_manager, f"get_{provider_id_key}", None)
        if getter:
            value = getter()
            if value:
                return str(value).strip() or None
    value = config_manager.get_llm_provider_id()
    return str(value).strip() if value else None


async def get_provider_id_with_fallback(
    context: Any,
    config_manager: ConfigManager,
    provider_id_key: str | None,
    umo: str | None = None,
) -> str | None:
    """Return the Bocchi model name selected by plugin configuration."""
    del context, umo
    return _configured_model(config_manager, provider_id_key, None)


async def call_provider_with_retry(
    context: Any,
    config_manager: ConfigManager,
    prompt: str,
    umo: str | None = None,
    provider_id_key: str | None = None,
    provider_id: str | None = None,
    system_prompt: str | None = None,
    response_format: JSONObject | None = None,
    extra_generate_kwargs: dict[str, JSONValue] | None = None,
) -> LLMResponse | None:
    """Call Bocchi's unified AI service while retaining the old retry contract."""
    del context, umo, response_format, extra_generate_kwargs
    if not prompt or not prompt.strip():
        logger.error("LLM prompt 为空，无法调用")
        return None

    model = _configured_model(config_manager, provider_id_key, provider_id)
    retries = max(1, int(config_manager.get_llm_retries()))
    backoff = max(0, float(config_manager.get_llm_backoff()))
    messages: list[LLMMessage] = []
    if system_prompt:
        messages.append(LLMMessage.system(system_prompt))
    messages.append(LLMMessage.user(prompt))

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(
                f"[LLM 调用] 尝试 #{attempt} | 模型: {model or 'Bocchi 全局默认'} | "
                f"prompt长度={len(prompt)}字符"
            )
            async with GlobalRateLimiter.get_instance().semaphore:
                result = await generate(messages=messages, model=model)
            return LLMResponse(
                completion_text=result.text,
                usage=result.usage_info,
                raw_completion=result.raw_response,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(f"[LLM 调用] 第 {attempt} 次请求失败: {exc}")
            if attempt < retries:
                await asyncio.sleep(backoff * (2 ** (attempt - 1)) + random.random())

    logger.error(f"LLM 请求重试耗尽: {last_error}")
    return None


def extract_token_usage(response: Any) -> dict[str, int]:
    token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    usage = getattr(response, "usage", None)
    if not usage:
        return token_usage
    if not isinstance(usage, dict):
        usage = vars(usage)
    token_usage["prompt_tokens"] = int(
        usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
    )
    token_usage["completion_tokens"] = int(
        usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
    )
    token_usage["total_tokens"] = int(
        usage.get("total_tokens", 0)
        or token_usage["prompt_tokens"] + token_usage["completion_tokens"]
    )
    return token_usage


def extract_response_text(response: Any) -> str:
    try:
        return str(getattr(response, "completion_text", response))
    except Exception as exc:
        logger.error(f"提取响应文本失败: {exc}")
        return ""
