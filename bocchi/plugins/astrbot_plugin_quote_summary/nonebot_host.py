"""NoneBot runtime adapters for persistence, bots, scheduling and rendering."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import nonebot
from nonebot.adapters.onebot.v11 import Bot
from nonebot_plugin_apscheduler import scheduler

from bocchi.configs.path_config import DATA_PATH

from .nonebot_config import MODULE_NAME
from .src.infrastructure.platform.adapters.onebot_adapter import OneBotAdapter


class KVStoreHost:
    """Disk-backed implementation of the old plugin KV contract."""

    def __init__(self) -> None:
        self.data_dir = DATA_PATH / MODULE_NAME
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._kv_path = self.data_dir / "kv.json"
        self._kv_lock = asyncio.Lock()

    def _read_kv(self) -> dict[str, Any]:
        if not self._kv_path.exists():
            return {}
        try:
            return json.loads(self._kv_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_kv(self, values: dict[str, Any]) -> None:
        temporary = self._kv_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(values, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self._kv_path)

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        async with self._kv_lock:
            values = await asyncio.to_thread(self._read_kv)
            return values.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        async with self._kv_lock:
            values = await asyncio.to_thread(self._read_kv)
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
            await asyncio.to_thread(self._write_kv, values)

    def close(self) -> None:
        pass


class NoneBotManager:
    """OneBot-only bot registry matching the analysis service's expectations."""

    def __init__(self, config_manager: Any):
        self.config_manager = config_manager
        self._bot_instances: dict[str, Bot] = {}
        self._adapters: dict[str, OneBotAdapter] = {}

    def register(self, bot: Bot) -> str:
        platform_id = str(bot.self_id)
        self._bot_instances[platform_id] = bot
        adapter = OneBotAdapter(
            bot,
            {
                "bot_self_ids": list(
                    {platform_id, *self.config_manager.get_bot_self_ids()}
                ),
                "platform_id": platform_id,
                "enable_base64_image": self.config_manager.get_enable_base64_image(),
            },
        )
        self._adapters[platform_id] = adapter
        return platform_id

    def unregister(self, bot: Bot) -> None:
        platform_id = str(bot.self_id)
        self._bot_instances.pop(platform_id, None)
        self._adapters.pop(platform_id, None)

    async def auto_discover_bot_instances(self) -> None:
        for bot in nonebot.get_bots().values():
            if isinstance(bot, Bot):
                self.register(bot)

    def get_adapter(self, platform_id: str | None = None) -> OneBotAdapter | None:
        if platform_id and platform_id in self._adapters:
            return self._adapters[platform_id]
        if len(self._adapters) == 1:
            return next(iter(self._adapters.values()))
        return None

    def get_platform_count(self) -> int:
        return len(self._bot_instances)

    def get_platform_ids(self) -> list[str]:
        return list(self._bot_instances)

    def is_ready_for_auto_analysis(self) -> bool:
        return bool(self._bot_instances)

    def is_plugin_enabled(self, platform_id: str, plugin_name: str) -> bool:
        return platform_id in self._bot_instances

    def _detect_platform_name(self, bot: Any) -> str:
        return "onebot"

    def set_bot_instance(self, bot: Bot, platform_id: str | None = None) -> None:
        self.register(bot)

    def set_bot_self_ids(self, bot_ids: list[str]) -> None:
        for adapter in self._adapters.values():
            adapter.bot_self_ids = [str(bot_id) for bot_id in bot_ids]


def scheduler_context() -> SimpleNamespace:
    return SimpleNamespace(cron_manager=SimpleNamespace(scheduler=scheduler))


async def html_render(
    html: str,
    data: dict[str, Any] | None = None,
    return_url: bool = False,
    options: dict[str, Any] | None = None,
) -> bytes:
    """Adapt AstrBot's html_render callback to nonebot-plugin-htmlrender."""
    del data, return_url
    from nonebot_plugin_htmlrender import html_to_pic

    options = options or {}
    image_type = options.get("type", "png")
    quality = options.get("quality") if image_type == "jpeg" else None
    scale_map = {"normal": 1.0, "high": 1.3, "ultra": 1.8}
    scale = scale_map.get(
        str(options.get("device_scale_factor_level", "normal")), 1.0
    )
    return await html_to_pic(
        html=html,
        template_path=f"file://{Path(__file__).parent.resolve()}/",
        viewport={"width": 1000, "height": 10},
        type=image_type,
        quality=quality,
        device_scale_factor=scale,
        screenshot_timeout=int(options.get("timeout", 60_000)),
        full_page=bool(options.get("full_page", True)),
    )
