from abc import ABC, abstractmethod
from collections.abc import Callable
import inspect
import json
import re
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel, Field, create_model
from pydantic.fields import FieldInfo

from bocchi.services.ai.run.context import RunContext
from bocchi.services.ai.run.di import DependencyInjector
from bocchi.services.ai.utils import PermissionUtils
from bocchi.utils.pydantic_compat import model_json_schema


class FieldPermission(ABC):
    """字段级权限校验基类/协议"""

    @abstractmethod
    async def check(self, context: RunContext) -> bool:
        """返回当前上下文（用户）是否有权使用该字段"""
        pass


class RequireSuperUser(FieldPermission):
    """仅限超级管理员可见的字段参数"""

    async def check(self, context: RunContext) -> bool:
        return await PermissionUtils.check_superuser(context)


class RequireAdminLevel(FieldPermission):
    """仅限满足群等级要求的管理员可见的字段参数"""

    def __init__(self, min_level: int = 1):
        self.min_level = min_level

    async def check(self, context: RunContext) -> bool:
        return await PermissionUtils.check_admin_level(context, self.min_level)


def _parse_docstring(docstring: str | None) -> tuple[str, dict[str, str]]:
    """解析文档字符串，解耦提取主描述和参数描述"""
    if not docstring:
        return "", {}

    lines = docstring.strip().splitlines()
    main_desc_lines = []
    params: dict[str, str] = {}

    section_header = re.compile(r"^\s*(?:Args|Arguments|Parameters|参数)\s*[:：]\s*$")
    return_header = re.compile(r"^\s*(?:Returns|Return|返回)\s*[:：]\s*$")
    param_pattern = re.compile(r"^\s*(\**\w+)(?:\s*\(.*?\))?\s*[:：]\s*(.*)")

    current_section = "main"
    last_param = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_section == "main":
                main_desc_lines.append("")
            continue

        if section_header.match(line):
            current_section = "params"
            continue
        elif return_header.match(line):
            current_section = "returns"
            continue

        if current_section == "main":
            main_desc_lines.append(line.strip())
        elif current_section == "params":
            match = param_pattern.match(line)
            if match:
                param_name = match.group(1).lstrip("*")
                param_desc = match.group(2).strip()
                params[param_name] = param_desc
                last_param = param_name
            elif last_param and line.startswith(" ") and stripped:
                params[last_param] += f" {stripped}"

    main_desc = "\n".join(main_desc_lines).strip()
    return main_desc, params


def build_tool_model(
    func: Callable, strict: bool = False
) -> tuple[dict, type[BaseModel]]:
    """利用 pydantic.create_model 从函数签名动态构建绝对严谨的 JSON Schema 及验证模型"""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func, include_extras=True)
    _, doc_params = _parse_docstring(func.__doc__)

    field_definitions = {}

    for name, param in sig.parameters.items():
        if name in ("self", "cls", "args", "kwargs"):
            continue

        if DependencyInjector.can_resolve_statically(param):
            continue

        anno = type_hints.get(name, Any)
        desc = doc_params.get(name, "")
        default_val = param.default

        user_desc = None
        if isinstance(default_val, FieldInfo) and default_val.description:
            user_desc = default_val.description
        elif get_origin(anno) is Annotated:
            for arg in get_args(anno)[1:]:
                if isinstance(arg, FieldInfo) and arg.description:
                    user_desc = arg.description
                    break

        final_desc = user_desc or desc

        if isinstance(default_val, FieldInfo):
            field_info = default_val
            if not field_info.description and final_desc:
                field_info.description = final_desc
            field_definitions[name] = (anno, field_info)
        else:
            if default_val is inspect.Parameter.empty:
                field_info = Field(..., description=final_desc)
            else:
                field_info = Field(default=default_val, description=final_desc)
            field_definitions[name] = (anno, field_info)

    try:
        DynamicModel = create_model(
            f"DynamicToolModel_{func.__name__}", **field_definitions
        )
        schema_def = model_json_schema(DynamicModel, mode="serialization")
    except Exception as e:
        error_msg = str(e)
        raise ValueError(
            f"无法为工具 '{func.__name__}' 生成合法的 JSON Schema。\n"
            "原因：函数的参数中包含了大模型无法解析的复杂类型"
            "（如 Bot, Event, 自定义类等）。\n"
            "💡 修复建议：如果该参数是底层框架依赖（如需要用到 nonebot 的 Bot），"
            "请务必使用 `Inject.XXX` 进行注解声明（例如 `bot: Inject.Bot`），"
            "这样系统会自动将其隐藏，不会发给大模型。\n"
            f"底层报错：{error_msg}"
        ) from e

    schema_def.pop("title", None)
    if strict:
        schema_def["additionalProperties"] = False

    return schema_def, DynamicModel


def build_schema_hint(args_schema: type[BaseModel] | None) -> str:
    """
    构建友好的人类可读 Schema 提示，供大模型在参数错误时进行自愈反思。
    """
    if args_schema is None:
        return ""
    try:
        schema = model_json_schema(args_schema)
        props = schema.get("properties", {})
        req = schema.get("required", [])

        hint = (
            f"\n\n💡 [系统提示] 该工具期望的正确 JSON 参数格式为:\n"
            f"```json\n{json.dumps(props, ensure_ascii=False, indent=2)}\n```\n"
            f"必填字段: {req}"
        )
        return hint
    except Exception:
        return ""


async def prune_schema_by_permissions(
    model_class: type[BaseModel], context: RunContext, schema: dict[str, Any]
) -> dict[str, Any]:
    """根据当前运行时上下文 (RunContext) 动态裁剪无权限的 Schema 字段"""
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    fields_to_remove = []

    fields = getattr(
        model_class, "model_fields", getattr(model_class, "__fields__", {})
    )

    for field_name, field_info in fields.items():
        for meta in field_info.metadata:
            if isinstance(meta, FieldPermission):
                if not await meta.check(context):
                    fields_to_remove.append(field_name)
                break

    for field_name in fields_to_remove:
        properties.pop(field_name, None)
        if field_name in required:
            required.remove(field_name)

    if "required" in schema and not required:
        schema.pop("required", None)

    return schema


async def check_field_permissions(
    model_class: type[BaseModel], kwargs: dict[str, Any], context: RunContext
) -> None:
    """验证传入的参数是否绕过了权限限制"""
    fields = getattr(
        model_class, "model_fields", getattr(model_class, "__fields__", {})
    )
    for field_name, field_info in fields.items():
        if field_name in kwargs:
            for meta in field_info.metadata:
                if isinstance(meta, FieldPermission):
                    if not await meta.check(context):
                        from bocchi.services.ai.core.exceptions import ToolRetryError

                        raise ToolRetryError(
                            f"权限拒绝：您当前的用户身份无权使用参数 '{field_name}'。"
                            "请移除该参数后重新规划并调用此工具。"
                        )
                    break
