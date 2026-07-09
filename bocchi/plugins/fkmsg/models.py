from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Union

from nonebot.adapters.onebot.v11 import MessageSegment


# 用户ID的来源
class UserSource(Enum):
    AT_MENTION = auto()  # 来源于@
    RAW_ID = auto()      # 来源于QQ号

@dataclass
class ParsedNode:
    uin: str
    source: UserSource
    content: list[Union[str, "ParsedNode"]] = field(default_factory=list)

class ForwardNodeData(dict[str, Any]):
    name: str
    uin: str
    content: MessageSegment | list[MessageSegment | dict[str, Any]]

class ForwardNode(dict[str, Any]):
    type: str
    data: ForwardNodeData
