import re

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent


async def should_handle_fake_msg(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    if len(event.original_message) > 1 and event.original_message[0].type == "at":
        second_seg = event.original_message[1]
        if (second_seg.type == "text" and
                second_seg.data.get("text", "").strip().startswith("说")):
            return True

    first_seg = event.original_message[0]
    if first_seg.type == "text":
        if re.match(r"^\d{6,11}说", first_seg.data.get("text", "")):
            return True

    return False
