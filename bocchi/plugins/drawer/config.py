import time
from typing import Any

from bocchi.configs.config import Config


class DrawerConfig:
    cooldown_seconds = 15 * 60

    @staticmethod
    def _get_config() -> Any:
        return Config.get("drawer")

    @property
    def base_url(self) -> str:
        base_url = self._get_config().get("DRAWER_BASE_URL")
        return str(base_url).rstrip("/")

    @property
    def model(self) -> str:
        return str(self._get_config().get("DRAWER_MODEL"))

    @property
    def request_interval_seconds(self) -> int:
        raw_value = self._get_config().get("DRAWER_REQUEST_INTERVAL", 60)
        try:
            return max(1, int(raw_value))
        except (TypeError, ValueError):
            return 60

    @property
    def keys(self) -> list[str]:
        raw_keys = self._get_config().get("DRAWER_KEY")
        if isinstance(raw_keys, list):
            return [str(key).strip() for key in raw_keys if str(key).strip()]
        if raw_keys:
            key = str(raw_keys).strip()
            return [key] if key else []
        return []

    def __init__(self) -> None:
        self.key_times: dict[str, int] = {}

    def _sync_key_times(self) -> list[str]:
        keys = self.keys
        self.key_times = {key: self.key_times.get(key, 0) for key in keys}
        return keys

    def get_api_key(self) -> str | None:
        """返回当前可用 key；若未配置则返回 None。"""
        keys = self._sync_key_times()
        if not keys:
            return None
        now = int(time.time())
        sorted_keys = sorted(keys, key=lambda key: self.key_times.get(key, 0))
        for key in sorted_keys:
            if self.key_times.get(key, 0) <= now:
                return key
        return sorted_keys[0]

    def delay_key(self, key: str) -> None:
        """在限流后将 key 标记为冷却。"""
        self._sync_key_times()
        if key in self.key_times:
            self.key_times[key] = int(time.time()) + self.cooldown_seconds

drawer_config = DrawerConfig()
