import asyncio
from collections.abc import Awaitable, Callable
import heapq
import time
from typing import Any

from nonebot.utils import is_coroutine_callable

from bocchi.services.log import logger


class LifespanManager:
    """
    高精度资源生命周期调度器
    """

    def __init__(self):
        self._resources: dict[
            Any,
            tuple[
                float,
                float,
                Callable[[Any], Awaitable[Any] | Any],
                Callable[[], Awaitable[bool] | bool] | None,
            ],
        ] = {}
        self._heap: list[tuple[float, Any]] = []
        self._lock = asyncio.Lock()
        self._wakeup_event = asyncio.Event()
        self._watchdog_task: asyncio.Task | None = None

    def _ensure_watchdog(self):
        """确保后台看门狗任务正在运行"""
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def register(
        self,
        resource_id: Any,
        ttl: float,
        cleanup_callback: Callable,
        is_busy_callback: Callable[[], Awaitable[bool] | bool] | None = None,
    ):
        """
        将资源注册到生命周期管理器中。

        参数:
            resource_id: 资源的唯一标识符 (可以是字符串、数字或其他 Hashable 对象)。
            ttl: 资源的存活时间 (秒)。
            cleanup_callback: 资源过期时触发的回调函数，接收 resource_id 作为唯一参数。
            is_busy_callback: (可选) 延迟存活探针。在触发清理前调用，若返回 True 则放弃清理并自动续期。
        """  # noqa: E501
        if ttl <= 0:
            await self.unregister(resource_id)
            return
        async with self._lock:
            expire_time = time.time() + ttl
            self._resources[resource_id] = (
                expire_time,
                ttl,
                cleanup_callback,
                is_busy_callback,
            )
            heapq.heappush(self._heap, (expire_time, resource_id))
            self._wakeup_event.set()

        self._ensure_watchdog()

    async def touch(self, resource_id: Any, ttl: float):
        """刷新资源的存活时间，为其续命"""
        if ttl <= 0:
            await self.unregister(resource_id)
            return
        async with self._lock:
            if resource_id in self._resources:
                _, original_ttl, cb, is_busy = self._resources[resource_id]
                expire_time = time.time() + ttl
                self._resources[resource_id] = (expire_time, original_ttl, cb, is_busy)
                heapq.heappush(self._heap, (expire_time, resource_id))
                self._wakeup_event.set()

    async def unregister(self, resource_id: Any):
        """主动从管理器中注销资源 (不再触发超时回收)"""
        async with self._lock:
            self._resources.pop(resource_id, None)

    async def _watchdog_loop(self):
        """核心看门狗循环"""
        try:
            while True:
                await self._wakeup_event.wait()
                self._wakeup_event.clear()

                while True:
                    async with self._lock:
                        if not self._heap:
                            break
                        expire_time, res_id = self._heap[0]

                        if (
                            res_id not in self._resources
                            or self._resources[res_id][0] != expire_time
                        ):
                            heapq.heappop(self._heap)
                            continue

                    now = time.time()
                    sleep_time = expire_time - now

                    if sleep_time > 0:
                        try:
                            await asyncio.wait_for(
                                self._wakeup_event.wait(), timeout=sleep_time
                            )
                            self._wakeup_event.clear()
                            continue
                        except asyncio.TimeoutError:
                            pass

                    async with self._lock:
                        if (
                            res_id not in self._resources
                            or self._resources[res_id][0] != expire_time
                        ):
                            continue
                        _, original_ttl, cb, is_busy = self._resources[res_id]

                    is_active = False
                    if is_busy is not None:
                        try:
                            res = is_busy()
                            if isinstance(res, Awaitable):
                                is_active = await res
                            else:
                                is_active = res
                        except Exception as e:
                            logger.error(
                                f"执行资源存活探针失败: {e}", command="LifespanManager"
                            )

                    if is_active:
                        logger.debug(
                            f"探针检测到资源 '{res_id}' 仍在忙碌，"
                            f"已自动续期 ({original_ttl}s)。",
                            command="LifespanManager",
                        )
                        await self.touch(res_id, original_ttl)
                        continue

                    async with self._lock:
                        if (
                            res_id in self._resources
                            and self._resources[res_id][0] == expire_time
                        ):
                            self._resources.pop(res_id)
                            heapq.heappop(self._heap)
                        else:
                            continue

                    logger.info(
                        f"♻️ 资源 '{res_id}' 闲置超时，触发自动回收。",
                        command="LifespanManager",
                    )
                    try:
                        if is_coroutine_callable(cb):
                            await cb(res_id)
                        else:
                            cb(res_id)
                    except Exception as e:
                        logger.error(
                            f"回收资源 '{res_id}' 时发生业务异常: {e}",
                            command="LifespanManager",
                        )

        except asyncio.CancelledError:
            pass

    async def stop(self):
        """停止生命周期管理器"""
        if self._watchdog_task:
            self._watchdog_task.cancel()
