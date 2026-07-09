import asyncio
from collections.abc import Callable
import functools
import inspect
import threading


def wrap_to_async(func: Callable) -> Callable:
    """
    将任意类型的函数（同步、异步、同步生成器、异步生成器）统一包装为异步执行形态。
    确保不会阻塞主线程，并保留原函数的元数据和签名。
    """
    if getattr(func, "__is_async_wrapper__", False):
        return func

    if inspect.isasyncgenfunction(func) or inspect.iscoroutinefunction(func):
        return func

    if inspect.isgeneratorfunction(func):

        async def async_gen_wrapper(*args, **kwargs):
            loop = asyncio.get_running_loop()
            q = asyncio.Queue()
            _sentinel = object()

            def _sync_runner():
                try:
                    for item in func(*args, **kwargs):
                        asyncio.run_coroutine_threadsafe(q.put(item), loop).result()
                    asyncio.run_coroutine_threadsafe(q.put(_sentinel), loop).result()
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(q.put(e), loop).result()

            t = threading.Thread(target=_sync_runner)
            t.start()

            while True:
                item = await q.get()
                if item is _sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item

        functools.update_wrapper(async_gen_wrapper, func)
        setattr(async_gen_wrapper, "__is_async_wrapper__", True)
        setattr(async_gen_wrapper, "_is_async_gen", True)
        return async_gen_wrapper

    async def async_wrapper(*args, **kwargs):
        p_func = functools.partial(func, *args, **kwargs)
        return await asyncio.to_thread(p_func)

    functools.update_wrapper(async_wrapper, func)
    setattr(async_wrapper, "__is_async_wrapper__", True)
    setattr(async_wrapper, "_is_coroutine", True)
    return async_wrapper
