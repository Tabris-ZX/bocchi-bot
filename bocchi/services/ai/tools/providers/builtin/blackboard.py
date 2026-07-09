from typing import Any

from pydantic import Field, create_model

from bocchi.services.ai.core.exceptions import ToolRetryError
from bocchi.services.ai.run.blackboard import BlackboardManager
from bocchi.services.ai.tools.core.tool import FunctionTool
from bocchi.services.ai.tools.core.toolkit import BaseToolkit
from bocchi.services.ai.tools.models import ToolOptions, ToolResult
from bocchi.utils.pydantic_compat import model_fields


class BlackboardToolkit(BaseToolkit):
    """
    黑板工具箱，将底层的 BlackboardManager 桥接给大模型，提供动态的读写工具。
    """

    default_prefix = ""

    def __init__(self, manager: BlackboardManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.manager = manager
        self._injected_tools.extend(self._create_dynamic_tools())

    def _create_dynamic_tools(self) -> list[FunctionTool]:
        async def read_blackboard() -> ToolResult:
            """读取当前团队的全局共享黑板状态。"""
            content = await self.manager.read()
            return ToolResult(output=content)

        read_tool = FunctionTool(
            func=read_blackboard,
            name="read_blackboard",
            description="读取当前团队的全局共享黑板最新状态。当你需要获取最新数据或了解现状时请调用此工具。",
        )

        optional_fields = {}
        for field in model_fields(self.manager.schema):
            desc = (
                getattr(field.field_info, "description", None)
                if hasattr(field, "field_info")
                else None
            )
            optional_fields[field.name] = (
                field.annotation | None,
                Field(default=None, description=desc),
            )

        UpdateSchema = create_model(
            f"Update_{self.manager.schema.__name__}", **optional_fields
        )

        async def update_blackboard(**kwargs) -> ToolResult:
            valid_kwargs = {k: v for k, v in kwargs.items() if v is not None}
            if not valid_kwargs:
                return ToolResult(
                    output="警告：没有提供任何有效的更新字段，黑板状态未发生改变。"
                )
            try:
                res = await self.manager.update(**valid_kwargs)
                return ToolResult(output=res)
            except ValueError as e:
                raise ToolRetryError(str(e))

        update_tool = FunctionTool(
            func=update_blackboard,
            name="update_blackboard",
            description="局部更新全局黑板状态。请仅提供你需要修改的字段即可，不需要改变的字段请留空。",
            settings=ToolOptions(args_schema=UpdateSchema),
        )

        return [read_tool, update_tool]
