import asyncio
from collections.abc import Callable
from typing import ClassVar

import nonebot
from nonebot.utils import is_coroutine_callable

from bocchi.services.log import logger
from bocchi.utils.enum import PriorityLifecycleType
from bocchi.utils.exception import HookPriorityException

driver = nonebot.get_driver()


class PriorityLifecycle:
    _data: ClassVar[dict[PriorityLifecycleType, dict[int, list[Callable]]]] = {}

    @classmethod
    def add(cls, hook_type: PriorityLifecycleType, func: Callable, priority: int):
        if hook_type not in cls._data:
            cls._data[hook_type] = {}
        if priority not in cls._data[hook_type]:
            cls._data[hook_type][priority] = []
        cls._data[hook_type][priority].append(func)

    @classmethod
    def on_startup(cls, *, priority: int):
        def wrapper(func):
            cls.add(PriorityLifecycleType.STARTUP, func, priority)
            return func

        return wrapper

    @classmethod
    def on_shutdown(cls, *, priority: int):
        def wrapper(func):
            cls.add(PriorityLifecycleType.SHUTDOWN, func, priority)
            return func

        return wrapper


async def _run_hook(func: Callable, priority: int, hook_type: str = "startup") -> None:
    logger.debug(f"执行优先级 [{priority}] on_{hook_type} 方法: {func.__module__}")
    if is_coroutine_callable(func):
        await func()
    else:
        func()


@driver.on_startup
async def _():
    priority_data = PriorityLifecycle._data.get(PriorityLifecycleType.STARTUP)
    if not priority_data:
        return
    priority_list = sorted(priority_data.keys())
    priority = 0
    try:
        for priority in priority_list:
            funcs = priority_data[priority]
            if len(funcs) == 1:
                await _run_hook(funcs[0], priority)
            else:
                await asyncio.gather(*[_run_hook(f, priority) for f in funcs])
    except HookPriorityException as e:
        logger.error(f"打断优先级 [{priority}] on_startup 方法. {type(e)}: {e}")


@driver.on_shutdown
async def _():
    priority_data = PriorityLifecycle._data.get(PriorityLifecycleType.SHUTDOWN)
    if not priority_data:
        return
    priority_list = sorted(priority_data.keys())
    for priority in priority_list:
        funcs = priority_data[priority]
        for func in funcs:
            try:
                await _run_hook(func, priority, "shutdown")
            except Exception as e:
                logger.error(f"执行优先级 [{priority}] on_shutdown 方法出错: {e}")
