from bocchi.utils.manager.priority_manager import PriorityLifecycle

from .engine import engine_manager
from .service import RendererService
from .types import Renderable, RenderResult

renderer_service = RendererService()


@PriorityLifecycle.on_startup(priority=10)
async def _init_renderer_service():
    """在Bot启动时初始化渲染服务及其依赖。"""
    await renderer_service.initialize()


@PriorityLifecycle.on_shutdown(priority=10)
async def _shutdown_renderer_service():
    """在Bot关闭时回收截图引擎资源。"""
    await engine_manager.close()


__all__ = ["RenderResult", "Renderable", "renderer_service"]
