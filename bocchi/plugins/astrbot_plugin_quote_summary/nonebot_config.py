"""Configuration bridge between Bocchi's flat registry and the plugin schema."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from bocchi.configs.config import Config

MODULE_NAME = "qq_group_daily_analysis"
CONFIG_KEY = "config"


def _schema_defaults(node: dict[str, Any]) -> Any:
    if node.get("type") == "object":
        return {
            key: _schema_defaults(value)
            for key, value in node.get("items", {}).items()
        }
    return copy.deepcopy(node.get("default"))


def load_defaults() -> dict[str, Any]:
    schema_path = Path(__file__).with_name("_conf_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return {key: _schema_defaults(value) for key, value in schema.items()}


def _merge_defaults(defaults: dict[str, Any], configured: Any) -> dict[str, Any]:
    result = copy.deepcopy(defaults)
    if not isinstance(configured, dict):
        return result
    for key, value in configured.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_defaults(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class BocchiPluginConfig(dict):
    """Mutable nested config with AstrBot-compatible persistence methods."""

    @classmethod
    def load(cls) -> "BocchiPluginConfig":
        defaults = load_defaults()
        Config.add_plugin_config(
            MODULE_NAME,
            CONFIG_KEY,
            defaults,
            default_value=defaults,
            type=dict,
            help="群日常分析完整配置（沿用原插件分组结构）",
        )
        configured = Config.get_config(MODULE_NAME, CONFIG_KEY, defaults)
        return cls(_merge_defaults(defaults, configured))

    def save_config(self) -> None:
        Config.set_config(MODULE_NAME, CONFIG_KEY, dict(self), auto_save=True)

    def reload_config(self) -> None:
        Config.reload()
        self.clear()
        self.update(self.load())
