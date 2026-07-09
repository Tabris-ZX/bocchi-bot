import asyncio
import json
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from bocchi.utils.pydantic_compat import (
    model_dump,
    model_json_schema,
    model_validate,
)

T = TypeVar("T", bound=BaseModel)


class BlackboardManager(Generic[T]):
    """
    结构化黑板管理器，提供带锁的并发读写和 Schema 校验。
    解决多智能体 (Team) 并发状态竞争及无结构脏写的问题。
    """

    def __init__(self, schema: type[T], initial_state: T | None = None):
        self.schema = schema
        if initial_state is not None:
            self._state = initial_state
        else:
            try:
                self._state = schema()
            except ValidationError as e:
                raise ValueError(
                    "初始化黑板状态失败，因为 Schema 存在无默认值的必填字段，"
                    f"请显式提供 initial_state: {e}"
                )

        self._lock = asyncio.Lock()

    async def read(self) -> str:
        """安全读取当前状态的 JSON 字符串表示"""
        async with self._lock:
            state_dict = model_dump(self._state)
            return json.dumps(state_dict, ensure_ascii=False)

    async def update(self, **kwargs: Any) -> str:
        """部分更新状态"""
        async with self._lock:
            current_dict = model_dump(self._state)

            def deep_update(d: dict, u: dict) -> dict:
                for k, v in u.items():
                    if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                        deep_update(d[k], v)
                    elif isinstance(v, list) and k in d and isinstance(d[k], list):
                        d[k].extend(x for x in v if x not in d[k])
                    else:
                        d[k] = v
                return d

            merged_dict = deep_update(current_dict, kwargs)

            try:
                new_state = model_validate(self.schema, merged_dict)
                self._state = new_state
                return "全局黑板状态更新成功"
            except ValidationError as e:
                error_msgs = []
                for err in e.errors():
                    loc = ".".join(str(x) for x in err["loc"])
                    msg = err.get("msg", "")
                    error_msgs.append(f"字段 `{loc}`: {msg}")
                err_msg = "\n".join(error_msgs)
                raise ValueError(f"黑板状态更新失败，非法的数据格式:\n{err_msg}")

    def get_schema(self) -> dict[str, Any]:
        """获取结构化 Schema"""
        return model_json_schema(self.schema)
