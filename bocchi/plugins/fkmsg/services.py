import traceback

from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.log import logger

from .models import ForwardNode, ForwardNodeData, ParsedNode, UserSource


async def _get_user_nickname(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    user_id: str,
    source: UserSource
) -> str:
    try:
        user_id_int = int(user_id)
        if isinstance(event, GroupMessageEvent) and source == UserSource.AT_MENTION:
            logger.debug(f"Fetching group nickname for {user_id} (from @).")
            member_info = await bot.get_group_member_info(
                group_id=event.group_id, user_id=user_id_int
            )
            return member_info.get("card") or member_info.get("nickname") or f"User_{user_id}"
        else:
            logger.debug(f"获取全局昵称 for {user_id}")
            user_info = await bot.get_stranger_info(user_id=user_id_int)
            return user_info.get("nickname") or f"User_{user_id}"

    except Exception as e:
        logger.error(f"获取用户 {user_id} 昵称失败: {e}")
        return f"User_{user_id}"

async def build_forward_nodes(
    parsed_nodes: list[ParsedNode],
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    images: list[MessageSegment]
) -> list[ForwardNode]:
    final_nodes: list[ForwardNode] = []

    for i, p_node in enumerate(parsed_nodes):
        content_segments = []
        for item in p_node.content:
            if isinstance(item, str):
                content_segments.append(MessageSegment.text(item))
            elif isinstance(item, ParsedNode):
                nested_forward_nodes = await build_forward_nodes([item], bot, event, [])
                if nested_forward_nodes:
                    content_segments.extend(nested_forward_nodes)

        if i == len(parsed_nodes) - 1 and images:
            content_segments.extend(images)

        nickname = await _get_user_nickname(bot, event, p_node.uin, p_node.source)

        node_data = ForwardNodeData(name=nickname, uin=p_node.uin, content=content_segments)
        final_nodes.append(ForwardNode(type="node", data=node_data))

    return final_nodes

async def send_forward_msg(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    nodes: list[ForwardNode]
):
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
        else:
            await bot.send_private_forward_msg(user_id=event.user_id, messages=nodes)
        logger.info(f"成功发送 {len(nodes)} 条假消息节点。")
    except Exception as e:
        error_msg = f"发送转发消息失败: {e}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        await bot.send(event, error_msg)
