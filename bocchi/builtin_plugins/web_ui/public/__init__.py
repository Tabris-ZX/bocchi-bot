from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bocchi.configs.path_config import DATA_PATH
from bocchi.services.log import logger

WEBUI_PATH = DATA_PATH / "web_ui" / "public"

router = APIRouter()


@router.get("/")
async def index():
    return FileResponse(WEBUI_PATH / "index.html")


@router.get("/favicon.ico")
async def favicon():
    return FileResponse(WEBUI_PATH / "favicon.ico")


async def init_public(app: FastAPI):
    try:
        if not WEBUI_PATH.exists() or not any(WEBUI_PATH.iterdir()):
            logger.warning("WebUI 资源不存在，请手动放置到 data/web_ui/public/", "WebUI")
            return
        folders = [
            x.name for x in WEBUI_PATH.iterdir() if x.is_dir()
        ]
        app.include_router(router)
        for pathname in folders:
            logger.debug(f"挂载文件夹: {pathname}")
            app.mount(
                f"/{pathname}",
                StaticFiles(
                    directory=WEBUI_PATH / pathname,
                    check_dir=True,
                ),
                name=f"public_{pathname}",
            )
    except Exception as e:
        logger.error("初始化 WebUI资源 失败", "WebUI", e=e)
