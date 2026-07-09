from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_session import EventSession

from bocchi.configs.path_config import IMAGE_PATH
from bocchi.configs.utils import BaseBlock, Command, PluginExtraData
from bocchi.services.log import logger
from bocchi.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="请我喝杯咖啡吧",
    description="想请作者喝杯咖啡吗,满足你!",
    usage="""
    为爱发电/打赏/vivo50/凉乞钞/喝咖啡
    """.strip(),
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="0.1",
    ).to_dict(),
)

_contribution_matcher = on_alconna(
    Alconna("为爱发电"),
    aliases={"打赏","vivo50","凉乞钞","喝咖啡"},
    priority=5,
    block=True,
)


@_contribution_matcher.handle()
async def _(session: EventSession):
    """处理贡献命令"""
    try:
        # 构建图片路径
        image_path = IMAGE_PATH / "contribution.png"
        
        # 检查图片是否存在
        if not image_path.exists():
            await MessageUtils.build_message("贡献图片不存在，请联系管理员").finish()
            return
        
        # 发送图片
        await MessageUtils.build_message(image_path).send()
        logger.info("贡献图片发送成功", "贡献插件", session=session)
        
    except Exception as e:
        logger.error(f"发送贡献图片失败: {e}", "贡献插件", e=e, session=session)
        await MessageUtils.build_message("发送贡献图片失败，请稍后重试").finish()
