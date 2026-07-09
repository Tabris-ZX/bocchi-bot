from pathlib import Path

import aiofiles
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from bocchi.configs.path_config import DATA_PATH
from bocchi.configs.utils import PluginExtraData
from bocchi.services.log import logger
from bocchi.utils.message import MessageUtils
from bocchi.utils.platform import PlatformUtils

__plugin_meta__ = PluginMetadata(
    name="关于",
    description="想要更加了解波奇吗",
    usage="""
    指令：
        关于
    """.strip(),
    extra=PluginExtraData(author="HibiKier", version="0.1", menu_type="其他").to_dict(),
)


_matcher = on_alconna(Alconna("关于"), priority=5, block=True, rule=to_me())


QQ_INFO = """
『后藤一里Bot』
版本：{version}
作者: Tabris
简介：参照基于Nonebot2开发的后藤一里Bot客制化，支持多平台的个性化Bot.将原Bot的人设改为作者钟爱的小孤独,集成了多个开源插件丰富了原Bot功能,也添加了作者的一些原创功能.后续会添加更多功能!
项目地址: https://github.com/Tabris-ZX/bocchi.git (波奇Bot)
参照项目: https://github.com/bocchi-org/bocchi_bot (波奇Bot)
""".strip()

INFO = """
『后藤一里Bot』
版本：{version}
作者: Tabris
简介：参照基于Nonebot2开发的后藤一里Bot客制化，支持多平台的个性化Bot.将原Bot的人设改为作者钟爱的小孤独,集成了多个开源插件丰富了原Bot功能,也添加了作者的一些原创功能.后续会添加更多功能!
项目地址: https://github.com/Tabris-ZX/bocchi.git (波奇Bot)
参照项目: https://github.com/bocchi-org/bocchi_bot (波奇Bot)
""".strip()


@_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    ver_file = Path() / "__version__"
    version = None
    if ver_file.exists():
        async with aiofiles.open(ver_file, encoding="utf8") as f:
            if text := await f.read():
                version = text.split(":")[-1].strip()
    if PlatformUtils.is_qbot(session):
        result: list[str | Path] = [QQ_INFO.format(version=version)]
        path = DATA_PATH / "about.png"
        if path.exists():
            result.append(path)
        await MessageUtils.build_message(result).send()  # type: ignore
    else:
        await MessageUtils.build_message(INFO.format(version=version)).send()
        logger.info("查看关于", arparma.header_result, session=session)
