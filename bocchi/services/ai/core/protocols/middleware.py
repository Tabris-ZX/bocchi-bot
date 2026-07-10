"""
LLM 中间件协议定义
"""

from __future__ import annotations

from typing import Protocol

from bocchi.services.ai.core.models import LLMContext, TReq, TRes


class NextCall(Protocol[TReq, TRes]):
    """中间件管道中下一个节点（或最终执行函数）的调用签名"""

    async def __call__(self, context: LLMContext[TReq, TRes], /) -> TRes: ...


class LLMMiddleware(Protocol[TReq, TRes]):
    """LLM 中间件函数的调用签名，遵循洋葱模型嵌套包裹设计"""

    async def __call__(
        self, context: LLMContext[TReq, TRes], next_call: NextCall[TReq, TRes], /
    ) -> TRes: ...
