from abc import ABC
from collections.abc import Callable
from enum import Enum
import inspect
from typing import Any

from nonebot.utils import is_coroutine_callable
from pydantic import BaseModel, Field

from bocchi.services.ai.core.exceptions import (
    GuardrailFatalException,
    GuardrailViolationError,
)
from bocchi.services.ai.core.messages import ChatResponse, LLMMessage, TextPart
from bocchi.services.ai.run.context import RunContext


class GuardrailAction(str, Enum):
    PASS = "PASS"
    """放行"""
    REJECT = "REJECT"
    """致命拦截：直接中断大模型思考"""
    REFLECT = "REFLECT"
    """打回反思：触发自愈闭环"""
    MUTATE = "MUTATE"
    """数据变异：就地修改数据后放行"""


class GuardrailResult(BaseModel):
    """护栏验证结果的统一载体"""

    action: GuardrailAction = GuardrailAction.PASS
    """验证动作（放行、拦截、反思、变异）"""

    feedback: str | None = None
    """未通过时的校验失败反馈原因或拒绝理由"""

    mutated_text: str | None = None
    """变异后的新文本内容（MUTATE 模式下生效）"""

    mutated_obj: Any | None = None
    """变异后的新解析对象（MUTATE 模式下生效）"""

    @property
    def success(self) -> bool:
        return self.action == GuardrailAction.PASS


def input_guardrail(func: Callable | None = None, *, max_attempts: int = 0):
    """显式标记为输入护栏。支持指定最大评估次数 (max_attempts)"""

    def decorator(f: Callable):
        setattr(f, "__guardrail_type__", "input")
        setattr(f, "__guardrail_max_attempts__", max_attempts)
        return f

    return decorator(func) if func else decorator


def output_guardrail(func: Callable | None = None, *, max_attempts: int = 0):
    """显式标记为输出护栏。支持指定最大评估次数 (max_attempts)"""

    def decorator(f: Callable):
        setattr(f, "__guardrail_type__", "output")
        setattr(f, "__guardrail_max_attempts__", max_attempts)
        return f

    return decorator(func) if func else decorator


class BaseGuardrail(ABC):
    """大一统的业务逻辑护栏抽象基类"""

    max_attempts: int = 0
    """当前护栏在单次上下文中允许触发的最大评估/拦截次数。0 代表无限制。"""

    async def validate_input(
        self, messages: list[LLMMessage], context: RunContext | None = None
    ) -> GuardrailResult:
        """执行输入拦截与变异逻辑"""
        return GuardrailResult(action=GuardrailAction.PASS)

    async def validate_output(
        self,
        response: ChatResponse | str,
        parsed_obj: Any,
        context: RunContext | None = None,
    ) -> GuardrailResult:
        """执行输出反思、拦截与变异逻辑"""
        return GuardrailResult(action=GuardrailAction.PASS)


class FunctionalGuardrail(BaseGuardrail):
    """包装普通 Python 函数的智能护栏"""

    def __init__(self, func: Callable[..., Any]):
        self.func = func
        self.guardrail_type = getattr(func, "__guardrail_type__", None)
        self.max_attempts = getattr(func, "__guardrail_max_attempts__", 0)

        if not self.guardrail_type:
            sig = inspect.signature(func)
            is_input = False
            is_output = False
            for param in sig.parameters.values():
                if param.annotation == inspect.Parameter.empty:
                    continue
                anno_str = str(param.annotation)
                if "LLMMessage" in anno_str:
                    is_input = True
                if "ChatResponse" in anno_str:
                    is_output = True

            if is_input and not is_output:
                self.guardrail_type = "input"
            elif is_output and not is_input:
                self.guardrail_type = "output"
            else:
                raise ValueError(
                    "无法自动推断护栏函数 '{func.__name__}' 的作用阶段。\n"
                    "请使用明确的类型注解 (如 list[LLMMessage] 或 ChatResponse)，\n"
                    "或使用 @input_guardrail / @output_guardrail 装饰器明确声明。"
                )

    def _bind_core_args(
        self, sig: inspect.Signature, core_arg_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """将框架提供的核心参数按名称或位置绑定到用户的签名上"""
        from bocchi.services.ai.run.di import DependencyInjector

        bound_kwargs = {}

        unmapped_cores = []
        for core_name, core_val in core_arg_dict.items():
            if core_name in sig.parameters:
                bound_kwargs[core_name] = core_val
            else:
                unmapped_cores.append(core_val)

        if unmapped_cores:
            val_idx = 0
            for name, param in sig.parameters.items():
                if name in ("self", "cls") or name in bound_kwargs:
                    continue
                if DependencyInjector.can_resolve_statically(param):
                    continue

                bound_kwargs[name] = unmapped_cores[val_idx]
                val_idx += 1
                if val_idx >= len(unmapped_cores):
                    break

        return bound_kwargs

    async def _execute_with_di(
        self, core_args: dict[str, Any], context: RunContext | None, is_input: bool
    ) -> GuardrailResult:
        """统一执行带有 DI 依赖注入的护栏逻辑"""
        from bocchi.services.ai.run.di import DependencyInjector

        safe_context = context or RunContext()

        try:
            sig = inspect.signature(self.func)
            call_kwargs = self._bind_core_args(sig, core_args)
            resolved_kwargs = await DependencyInjector.resolve_all(
                sig=sig, call_kwargs=call_kwargs, context=safe_context
            )
            filtered_kwargs = {
                k: v for k, v in resolved_kwargs.items() if k in sig.parameters
            }

            res = (
                await self.func(**filtered_kwargs)
                if is_coroutine_callable(self.func)
                else self.func(**filtered_kwargs)
            )
            return self._parse_result(res, is_input=is_input)
        except (ValueError, AssertionError) as e:
            action = GuardrailAction.REJECT if is_input else GuardrailAction.REFLECT
            return GuardrailResult(action=action, feedback=str(e))
        except Exception as e:
            from bocchi.services.ai.core.exceptions import ControlFlowExit

            if isinstance(e, ControlFlowExit):
                raise
            action = GuardrailAction.REJECT if is_input else GuardrailAction.REFLECT
            stage_str = "输入" if is_input else "输出"
            return GuardrailResult(
                action=action, feedback=f"{stage_str}护栏执行异常: {e}"
            )

    async def validate_input(
        self, messages: list[LLMMessage], context: RunContext | None = None
    ) -> GuardrailResult:
        if self.guardrail_type != "input":
            return GuardrailResult(action=GuardrailAction.PASS)
        return await self._execute_with_di(
            {"messages": messages}, context, is_input=True
        )

    async def validate_output(
        self,
        response: ChatResponse | str,
        parsed_obj: Any,
        context: RunContext | None = None,
    ) -> GuardrailResult:
        if self.guardrail_type != "output":
            return GuardrailResult(action=GuardrailAction.PASS)
        return await self._execute_with_di(
            {"response": response, "parsed_obj": parsed_obj}, context, is_input=False
        )

    def _parse_result(self, res: Any, is_input: bool) -> GuardrailResult:
        """统一处理返回值类型推导"""
        if isinstance(res, GuardrailResult):
            return res

        if res is False:
            action = GuardrailAction.REJECT if is_input else GuardrailAction.REFLECT
            return GuardrailResult(
                action=action,
                feedback=f"自定义护栏函数 '{self.func.__name__}' 校验未通过",
            )
        elif isinstance(res, str):
            action = GuardrailAction.REJECT if is_input else GuardrailAction.REFLECT
            return GuardrailResult(action=action, feedback=res)

        return GuardrailResult(action=GuardrailAction.PASS)


class JudgeViolation(BaseModel):
    rule: str
    """违反的规则内容"""

    reason: str
    """违反该规则的具体原因和证据。如果没有违反，填无"""


class JudgeResponse(BaseModel):
    passed: bool
    """文本是否完全遵守了所有的规则。如果有任何一条违反，此处必须为 False"""

    violations: list[JudgeViolation] = Field(default_factory=list)
    """违反的规则列表及原因。如果没有违反，返回空列表"""


class LLMJudgeConfig(BaseModel):
    """LLM 裁判的全局设定"""

    judge_model: str | None = None
    """指定的裁判模型名称，如果为空则优先使用当前对话模型，其次为全局默认模型"""

    system_prompt_template: str | None = None
    """自定义裁判 Prompt 模板。必须包含 {rules} 和 {text} 占位符"""

    max_attempts: int = 0
    """最大裁判评估次数。超过该次数后大模型裁判自动放弃并放行 (0 表示无限制)"""


class LLMGuardrail(BaseGuardrail):
    """基于 LLM-as-a-Judge 的自然语言规则裁判护栏"""

    def __init__(self, rules: list[str], config: LLMJudgeConfig | None = None):
        self.rules = rules
        self.config = config or LLMJudgeConfig()
        self.max_attempts = self.config.max_attempts

    async def validate_output(
        self,
        response: ChatResponse | str,
        parsed_obj: Any,
        context: RunContext | None = None,
    ) -> GuardrailResult:
        if not self.rules:
            return GuardrailResult(action=GuardrailAction.PASS)

        text = response if isinstance(response, str) else response.text
        from bocchi.services.ai.llm.api import generate_structured
        from bocchi.services.ai.llm.manager import get_default_model

        rules_str = "\n".join([f"{i + 1}. {r}" for i, r in enumerate(self.rules)])
        if self.config.system_prompt_template:
            prompt = self.config.system_prompt_template.format(
                rules=rules_str, text=text
            )
        else:
            prompt = (
                "你是一个严格的内容风控与业务合规裁判。\n"
                "请评估以下[待检测内容]是否违反了任何一条[规则列表]。\n\n"
                f"### [规则列表]\n{rules_str}\n\n"
                f"### [待检测内容]\n{text}\n\n"
                "请严格按照规则评估。只要违反了其中任意一条，"
                "passed 必须为 false，并在 violations 中详细说明理由。"
            )

        model = self.config.judge_model
        if not model and context and context.run.current_model:
            model = context.run.current_model
        if not model:
            model = get_default_model("chat")

        try:
            res = await generate_structured(
                prompt, response_model=JudgeResponse, model=model
            )
            if res.passed:
                return GuardrailResult(action=GuardrailAction.PASS)
            feedbacks = [
                f"违反规则: 【{v.rule}】, 原因: {v.reason}" for v in res.violations
            ]
            return GuardrailResult(
                action=GuardrailAction.REFLECT, feedback="\n".join(feedbacks)
            )
        except Exception as e:
            return GuardrailResult(
                action=GuardrailAction.REFLECT, feedback=f"系统护栏裁判模型异常: {e}"
            )


GuardrailSource = Callable[..., Any] | str | BaseGuardrail | LLMJudgeConfig
"""护栏来源（函数、自然语言规则、BaseGuardrail 实例或裁判配置）"""


def parse_guardrails(guardrails: list[GuardrailSource] | None) -> list[BaseGuardrail]:
    """工具方法：将各种类型的 Guardrail 解析为标准的 BaseGuardrail 列表"""
    v_list = []
    llm_rules = []
    judge_config = None
    for v in guardrails or []:
        if isinstance(v, BaseGuardrail):
            v_list.append(v)
        elif callable(v):
            v_list.append(FunctionalGuardrail(v))
        elif isinstance(v, str):
            llm_rules.append(v)
        elif isinstance(v, LLMJudgeConfig):
            judge_config = v

    if llm_rules:
        v_list.append(LLMGuardrail(rules=llm_rules, config=judge_config))

    return v_list


class GuardrailPipeline:
    """护栏管线引擎"""

    def __init__(self, guardrails: list[BaseGuardrail]):
        self.guardrails = guardrails

    async def run_input_pipeline(
        self, messages: list[LLMMessage], context: RunContext | None = None
    ) -> list[LLMMessage]:
        """执行 Input 护栏拦截与变异"""
        for g in self.guardrails:
            if g.max_attempts > 0 and context:
                counts = context.state.setdefault("__guardrail_input_counts__", {})
                g_id = id(g)
                if counts.get(g_id, 0) >= g.max_attempts:
                    continue
                counts[g_id] = counts.get(g_id, 0) + 1

            res = await g.validate_input(messages, context)
            if res.action == GuardrailAction.REJECT:
                raise GuardrailFatalException(
                    guard_name=g.__class__.__name__, reason=res.feedback or "输入被拦截"
                )
            elif (
                res.action == GuardrailAction.MUTATE
                and res.mutated_text is not None
                and messages
            ):
                text_replaced = False
                for p in messages[-1].content:
                    if isinstance(p, TextPart):
                        p.text = res.mutated_text
                        text_replaced = True
                        break
                if not text_replaced:
                    messages[-1].content.append(TextPart(text=res.mutated_text))
        return messages

    async def run_output_pipeline(
        self,
        response: ChatResponse | str,
        parsed_obj: Any,
        context: RunContext | None = None,
    ) -> tuple[ChatResponse | str, Any]:
        """执行 Output 护栏拦截、反思和变异"""
        feedbacks = []
        current_response = response
        current_obj = parsed_obj

        for g in self.guardrails:
            if g.max_attempts > 0 and context:
                counts = context.state.setdefault("__guardrail_output_counts__", {})
                g_id = id(g)
                if counts.get(g_id, 0) >= g.max_attempts:
                    continue
                counts[g_id] = counts.get(g_id, 0) + 1

            res = await g.validate_output(current_response, current_obj, context)
            if res.action == GuardrailAction.REJECT:
                raise GuardrailFatalException(
                    guard_name=g.__class__.__name__, reason=res.feedback or "输出被拒绝"
                )
            elif res.action == GuardrailAction.MUTATE:
                if res.mutated_text is not None:
                    if isinstance(current_response, str):
                        current_response = res.mutated_text
                    else:
                        text_found = False
                        for p in current_response.content_parts:
                            if isinstance(p, TextPart):
                                p.text = res.mutated_text
                                text_found = True
                                break
                        if not text_found:
                            current_response.content_parts.insert(
                                0, TextPart(text=res.mutated_text)
                            )
                if res.mutated_obj is not None:
                    current_obj = res.mutated_obj
            elif res.action == GuardrailAction.REFLECT:
                feedbacks.append(res.feedback or f"{g.__class__.__name__} 校验未通过")

        if feedbacks:
            raise GuardrailViolationError("\n".join(feedbacks))

        return current_response, current_obj
