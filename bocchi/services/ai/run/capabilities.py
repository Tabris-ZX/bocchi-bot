from __future__ import annotations

from collections import defaultdict

from bocchi.services.ai.capabilities import (
    AbstractCapability,
)
from bocchi.services.log import logger
from bocchi.utils.utils import infer_plugin_namespace

GLOBAL_CAPABILITIES: dict[str, list[AbstractCapability]] = defaultdict(list)

from bocchi.services.ai.capabilities.builtin import (
    BillingCapability,
    GlobalCycleLimitCapability,
    PermissionCapability,
    ReflexionCapability,
    StuckDetectionCapability,
    ToolRetryAndReflectionCapability,
)

for _cap in [
    GlobalCycleLimitCapability(),
    StuckDetectionCapability(),
    PermissionCapability(),
    BillingCapability(),
    ToolRetryAndReflectionCapability(),
    ReflexionCapability(),
]:
    GLOBAL_CAPABILITIES["global"].append(_cap)


def register_global_capability(
    capability: AbstractCapability, scope: str | None = None
) -> None:
    ns = scope if scope is not None else infer_plugin_namespace()
    GLOBAL_CAPABILITIES[ns].append(capability)
    logger.debug(
        f"已注册全局 Capability: {capability.__class__.__name__} -> Namespace: {ns}"
    )
