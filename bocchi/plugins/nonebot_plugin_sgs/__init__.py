from pathlib import Path
from nonebot import require
from nonebot.adapters.onebot.v11 import MessageSegment, GroupMessageEvent, PrivateMessageEvent
from nonebot.permission import SUPERUSER
alc_plugin = require("nonebot_plugin_alconna")
Alconna = alc_plugin.Alconna
Args = alc_plugin.Args
on_alconna = alc_plugin.on_alconna
from .util import Util
from .data_source import DataSource
from .config import Config
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="三国杀wiki",
    description="三国杀wiki查询助手",
    usage="""
    sgs ?[武将名称] : 查询武将信息
    sgs公告 : 查询三国杀wiki公告
    """,
    homepage="https://github.com/Tabris-ZX/nonebot-plugin-sgs.git",
    type="application",
    config=Config,
    supported_adapters={"~onebot.v11"}
)

sgs_info = on_alconna(
    Alconna("sgs",
        Args["name",str],
    ),
    priority=5,
    block=True,
)

sgs_news = on_alconna(
    Alconna("sgs公告"),
    priority=5,
    block=True,
)

sgs_clean_img=on_alconna(
    Alconna("sgs图片清理"),
    priority=5,
    block=True,
    permission=SUPERUSER,
)

@sgs_info.handle()
async def handle_sgs_info(name:str):
    msg = await DataSource.get_roles_info(name=name)
    if isinstance(msg, Path):
        await sgs_info.send(MessageSegment.image(msg))
    else:
        await sgs_info.finish(msg)

@sgs_news.handle()
async def handle_sgs_news():
    news_list = await DataSource.build_news_img()
    if len(news_list) == 0:
        await sgs_news.finish("没有找到公告")
    
    # 逐条发送图片
    for news in news_list:
        if isinstance(news, Path) and news.exists():
            try:
                await sgs_news.send(MessageSegment.image(news))
            except Exception as e:
                await sgs_news.send(f"发送图片失败: {e}")
                continue

@sgs_clean_img.handle()
async def handle_sgs_clean_img():
    await Util.clean_img()
    await sgs_clean_img.finish("图片清除完成")