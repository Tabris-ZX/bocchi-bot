import traceback
from typing import Union

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.plugin import PluginMetadata

from bocchi.configs.utils import PluginExtraData
from bocchi.services.log import logger

from .parser import parse_content
from .rules import should_handle_fake_msg
from .services import build_forward_nodes, send_forward_msg

__plugin_meta__ = PluginMetadata(
    name="伪造转发",
    description="伪造QQ聊天记录，生成转发消息",
    usage="""
    基本用法：
    1. @用户说 内容 - 生成一条指定用户说的转发消息
    2. QQ号说 内容 - 使用QQ号指定用户生成转发消息

    多条消息：
    使用 | 分隔不同用户的消息，
    如：@用户1说 你好 | @用户2说 你好啊

    嵌套消息：
    使用 { } 嵌套消息内容，
    如：@用户1说 看这个 | @用户1说 {@用户2说 这是嵌套消息}

    带图片：
    建议使用NTQQ来排版
    """.strip(),
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="1.0",
        menu_type="功能",
    ).dict(),
)

EventType = Union[GroupMessageEvent, PrivateMessageEvent]
fake_msg_handler = on_message(
    rule=should_handle_fake_msg,
    priority=5,
    block=True
)

@fake_msg_handler.handle()
async def _(bot: Bot, event: EventType):
    try:
        message = event.get_message()
        at_qq_list = [
            seg.data["qq"] for seg in message if seg.type == "at"
        ]
        image_segments = [
            seg for seg in message if seg.type == "image"
        ]
        raw_text = ""
        if at_qq_list:
            raw_text = message.extract_plain_text().lstrip(" ")
        else:
            raw_text = event.get_plaintext()

        parsed_nodes, _ = parse_content(raw_text, at_qq_list)

        if not parsed_nodes:
            await fake_msg_handler.finish("消息内容无效或为空")

        forward_nodes = await build_forward_nodes(
            parsed_nodes, bot, event, image_segments
        )

        if forward_nodes:
            await send_forward_msg(bot, event, forward_nodes)
        else:
            await fake_msg_handler.finish("生成消息失败")

    except Exception as e:
        error_msg = f"发生意外错误: {e}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        await fake_msg_handler.finish(error_msg)
