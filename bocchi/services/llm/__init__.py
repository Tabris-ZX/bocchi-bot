"""
向下兼容门面 (Facade)

利用 sys.modules 魔法，将对 bocchi.services.llm 及其子模块的导入
无缝重定向到 bocchi.services.ai.llm 下，避免破坏任何第三方插件。
同时在此提供最常用的类导出，作为 LLM 服务的统一入口。
"""

import sys
from types import ModuleType
from typing import Any

from bocchi.services import logger

logger.warning(
    "bocchi.services.llm 已被重构迁移至 bocchi.services.ai.llm，"
    "为了更好的性能和兼容性，请及时更新您的插件导入路径。"
)

from pydantic import BaseModel, ConfigDict

import bocchi.services.ai.core
import bocchi.services.ai.core.exceptions
import bocchi.services.ai.core.messages
from bocchi.services.ai.core.messages import ChatResponse as LLMResponse
from bocchi.services.ai.core.messages import LLMContentPart, ToolCallPart
import bocchi.services.ai.core.models
from bocchi.services.ai.core.models import ToolDefinition
import bocchi.services.ai.core.options
import bocchi.services.ai.core.protocols
from bocchi.services.ai.core.protocols.tool import ToolExecutable
import bocchi.services.ai.llm
import bocchi.services.ai.llm.system.capabilities
from bocchi.services.ai.run import RunContext as RealRunContext
import bocchi.services.ai.tools
from bocchi.services.ai.tools.models import ToolResult

_legacy_types_module = ModuleType("bocchi.services.llm.types")
for _mod in (
    bocchi.services.ai.core.options,
    bocchi.services.ai.core.exceptions,
    bocchi.services.ai.core.messages,
    bocchi.services.ai.core.models,
):
    for _name in dir(_mod):
        if not _name.startswith("_"):
            setattr(_legacy_types_module, _name, getattr(_mod, _name))

sys.modules["bocchi.services.llm.types"] = _legacy_types_module
sys.modules["bocchi.services.llm.types.models"] = bocchi.services.ai.core.models
sys.modules["bocchi.services.llm.types.protocols"] = bocchi.services.ai.core.protocols
sys.modules["bocchi.services.llm.types.exceptions"] = (
    bocchi.services.ai.core.exceptions
)
sys.modules["bocchi.services.llm.types.capabilities"] = (
    bocchi.services.ai.llm.system.capabilities
)

prefix_old = "bocchi.services.llm"
prefix_new = "bocchi.services.ai.llm"

for module_name, module_obj in list(sys.modules.items()):
    if module_name.startswith(prefix_new):
        old_module_name = module_name.replace(prefix_new, prefix_old, 1)
        if old_module_name not in sys.modules:
            sys.modules[old_module_name] = module_obj

sys.modules["bocchi.services.llm.tools"] = bocchi.services.ai.tools


class LLMToolFunction(BaseModel):
    name: str
    arguments: str


class LLMToolCall(BaseModel):
    id: str
    function: LLMToolFunction
    thought_signature: str | None = None
    type: str = "function"


class _FakeFunction:
    def __init__(self, name, args):
        self.name = name
        self.arguments = (
            args
            if isinstance(args, str)
            else __import__("json").dumps(args, ensure_ascii=False)
        )


@property
def _legacy_function(self) -> _FakeFunction:
    return _FakeFunction(self.tool_name, self.args)


setattr(ToolCallPart, "function", _legacy_function)  # type: ignore


@property
def _legacy_thought_signature(self) -> Any:
    return self.metadata.get("thought_signature") if self.metadata else None


@_legacy_thought_signature.setter
def _legacy_thought_signature(self, value: Any) -> None:
    if self.metadata is None:
        self.metadata = {}
    self.metadata["thought_signature"] = value


setattr(ToolCallPart, "thought_signature", _legacy_thought_signature)  # type: ignore

from bocchi.services.ai.core.messages import LLMMessage

_original_assistant_tool_calls = LLMMessage.assistant_tool_calls


@classmethod
def _shim_assistant_tool_calls(
    cls, tool_calls: Any, content: Any = "", scope: Any = None
) -> Any:
    converted = []
    for tc in tool_calls:
        if hasattr(tc, "function") and not isinstance(tc, ToolCallPart):
            converted.append(
                ToolCallPart(
                    id=tc.id, tool_name=tc.function.name, args=tc.function.arguments
                )
            )
        else:
            converted.append(tc)
    return _original_assistant_tool_calls(converted, content, scope)  # type: ignore


setattr(LLMMessage, "assistant_tool_calls", _shim_assistant_tool_calls)  # type: ignore

if not hasattr(LLMMessage, "name"):

    @property
    def _legacy_name(self) -> Any:
        return getattr(self, "source_name", None)

    @_legacy_name.setter
    def _legacy_name(self, value: Any) -> None:
        self.source_name = value

    setattr(LLMMessage, "name", _legacy_name)  # type: ignore

if not hasattr(LLMMessage, "tool_call_id"):

    @property
    def _legacy_tool_call_id(self) -> Any:
        return None

    @_legacy_tool_call_id.setter
    def _legacy_tool_call_id(self, value: Any) -> None:
        pass

    setattr(LLMMessage, "tool_call_id", _legacy_tool_call_id)  # type: ignore

from bocchi.services.ai.core.options import GenerationConfig, ReasoningEffort

mod_config_gen = ModuleType("bocchi.services.llm.config.generation")
sys.modules["bocchi.services.llm.config"] = ModuleType("bocchi.services.llm.config")
sys.modules["bocchi.services.llm.config.generation"] = mod_config_gen


class ReasoningConfig(BaseModel):
    model_config = ConfigDict(extra="allow")  # type: ignore


class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="allow")  # type: ignore


setattr(mod_config_gen, "LLMGenerationConfig", GenerationConfig)  # type: ignore
setattr(mod_config_gen, "ReasoningConfig", ReasoningConfig)  # type: ignore
setattr(mod_config_gen, "ToolConfig", ToolConfig)  # type: ignore
setattr(mod_config_gen, "ReasoningEffort", ReasoningEffort)  # type: ignore

_target_models_mod = sys.modules["bocchi.services.llm.types.models"]
setattr(_target_models_mod, "ToolResult", ToolResult)  # type: ignore
setattr(_target_models_mod, "LLMToolCall", LLMToolCall)  # type: ignore
setattr(_target_models_mod, "LLMToolFunction", LLMToolFunction)  # type: ignore
setattr(_target_models_mod, "LLMContentPart", LLMContentPart)  # type: ignore
setattr(_target_models_mod, "ToolDefinition", ToolDefinition)  # type: ignore
setattr(_target_models_mod, "LLMResponse", LLMResponse)  # type: ignore
setattr(_target_models_mod, "LLMMessage", LLMMessage)  # type: ignore
setattr(
    sys.modules["bocchi.services.llm.types.protocols"],
    "ToolExecutable",
    ToolExecutable,
)  # type: ignore


class LegacyRunContextShim:
    """拦截旧版 RunContext(extra={...}) 的调用，转化为新版支持的 state"""

    def __new__(cls, session_id=None, extra=None, scope=None, **kwargs):
        state = kwargs.get("state", {})
        if extra:
            state.update(extra)
        if scope:
            state.update(scope)
        ctx = RealRunContext(session_id=session_id, state=state)
        ctx.extra = ctx.state  # type: ignore
        ctx.scope = ctx.state  # type: ignore
        return ctx


setattr(sys.modules["bocchi.services.llm.tools"], "RunContext", LegacyRunContextShim)  # type: ignore


class ToolInvoker:
    """向下兼容垫片：代替被重构移除的旧版 ToolInvoker"""

    def __init__(self, callbacks=None):
        self.callbacks = callbacks or []

    async def execute_tool_call(self, tool_call, available_tools, context=None):
        import json

        if hasattr(tool_call, "function") and hasattr(tool_call.function, "name"):
            tool_name = tool_call.function.name
            args_raw = tool_call.function.arguments
        else:
            tool_name = getattr(tool_call, "tool_name", "unknown")
            args_raw = getattr(tool_call, "args", "{}")

        arguments = {}
        if args_raw:
            if isinstance(args_raw, str):
                try:
                    arguments = json.loads(args_raw)
                except Exception:
                    pass
            elif isinstance(args_raw, dict):
                arguments = args_raw

        executable = available_tools.get(tool_name)
        if not executable:
            return tool_call, ToolResult(output=f"Error: Tool '{tool_name}' not found.")

        try:
            result = await executable.execute(context=context, **arguments)
            if not hasattr(result, "output"):
                result = ToolResult(output=result)
            return tool_call, result
        except Exception as e:
            return tool_call, ToolResult(output=f"System Execution Error: {e!s}")


import bocchi.services.ai.tools

setattr(bocchi.services.ai.tools, "ToolInvoker", ToolInvoker)  # type: ignore
setattr(sys.modules["bocchi.services.llm.tools"], "ToolInvoker", ToolInvoker)  # type: ignore


class CommonOverrides:
    """向下兼容垫片：由于该类已被废弃，此处提供空实现以防止旧插件导入报错。"""

    @staticmethod
    def _fallback(*args, **kwargs):
        from bocchi.services.ai.llm.builder import IntentBuilder

        return IntentBuilder().build()

    gemini_json = _fallback
    gemini_2_5_thinking = _fallback
    gemini_3_thinking = _fallback
    gemini_structured = _fallback
    gemini_safe = _fallback
    gemini_code_execution = _fallback
    gemini_grounding = _fallback
    gemini_nano_banana = _fallback
    gemini_high_res = _fallback


from bocchi.services.ai.core.options import GenerationConfig, OutputFormatConfig


class OutputConfig(OutputFormatConfig):
    """向下兼容垫片：旧版 OutputConfig 等价于 OutputFormatConfig。"""


AIConfig = GenerationConfig
LLMGenerationConfig = GenerationConfig
from bocchi.services.ai.llm import *  # noqa: F403
from bocchi.services.ai.llm.manager import (
    get_default_model,
    get_model_instance,
    list_available_models,
    list_embedding_models,
)
from bocchi.services.ai.message_builder import MessageBuilder

message_to_unimessage = MessageBuilder.message_to_unimessage
unimsg_to_llm_parts = MessageBuilder.unimsg_to_llm_parts
from bocchi.services.ai.core.exceptions import LLMException
from bocchi.services.ai.core.messages import ChatRequest
from bocchi.services.ai.core.messages import ChatResponse as LLMResponse
from bocchi.services.ai.llm.api import generate_structured as _new_generate_structured
from bocchi.services.ai.llm.engine.router import LLMOrchestrator
from bocchi.services.ai.tools import tool as function_tool


class AI:
    """向下兼容垫片：代替被彻底删除的旧版 AI 类"""

    def __init__(self, session_id=None, **kwargs):
        self.session_id = session_id

    async def generate_internal(
        self,
        messages,
        model=None,
        config=None,
        tools=None,
        tool_choice=None,
        timeout=None,
    ):
        req = ChatRequest(
            messages=messages,
            config=config,
            tools=tools,
            tool_choice=tool_choice,
            timeout=timeout,
        )
        if self.session_id:
            req.extra["session_id"] = self.session_id
        return await LLMOrchestrator.invoke(req, model_name=model, task="chat")

    async def generate_structured(
        self,
        message,
        response_model,
        model=None,
        tools=None,
        tool_choice=None,
        instruction=None,
        timeout=None,
        template_vars=None,
        config=None,
        max_validation_retries=None,
        validation_callback=None,
        error_prompt_template=None,
        auto_thinking=False,
    ):
        return await _new_generate_structured(
            message=message,
            response_model=response_model,
            model=model,
            instruction=instruction,
            timeout=timeout,
            config=config,
            max_retries=max_validation_retries,
            error_prompt_template=error_prompt_template,
        )


__all__ = [
    "AI",
    "AIConfig",
    "CommonOverrides",
    "GenerationConfig",
    "LLMContentPart",
    "LLMException",
    "LLMGenerationConfig",
    "LLMMessage",
    "LLMResponse",
    "LLMToolCall",
    "LLMToolFunction",
    "OutputConfig",
    "ToolDefinition",
    "ToolExecutable",
    "ToolInvoker",
    "ToolResult",
    "function_tool",
    "get_default_model",
    "get_model_instance",
    "list_available_models",
    "list_embedding_models",
    "message_to_unimessage",
    "unimsg_to_llm_parts",
]
