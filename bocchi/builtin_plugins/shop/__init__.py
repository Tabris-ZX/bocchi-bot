from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Arparma,
    At,
    Match,
    MultiVar,
    Option,
    Query,
    Subcommand,
    UniMessage,
    UniMsg,
    on_alconna,
    store_true,
)
from nonebot_plugin_uninfo import Uninfo

from bocchi.configs.utils import BaseBlock, Command, PluginExtraData, RegisterConfig
from bocchi.services.log import logger
from bocchi.utils.decorator.shop import NotMeetUseConditionsException
from bocchi.utils.depends import UserName
from bocchi.utils.enum import BlockType, PluginType
from bocchi.utils.exception import GoodsNotFound
from bocchi.utils.message import MessageUtils
from bocchi.utils.platform import PlatformUtils

from ._data_source import ShopManage, gold_rank

__plugin_meta__ = PluginMetadata(
    name="商店",
    description="商店系统[金币回收计划]",
    usage="""
    商品操作
    指令：
        商店
        我的金币
        我的道具
        使用道具 [名称/Id]
        购买道具 [名称/Id]
        金币排行 ?[num=10]
        金币总排行 ?[num=10]
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.NORMAL,
        menu_type="商店",
        commands=[
            Command(command="商店"),
            Command(command="我的金币"),
            Command(command="我的道具"),
            Command(command="购买道具"),
            Command(command="使用道具"),
            Command(command="金币排行"),
            Command(command="金币总排行"),
        ],
        limits=[BaseBlock(check_type=BlockType.GROUP)],
        configs=[
            RegisterConfig(
                key="style",
                value="bocchi",
                help="商店样式类型，[normal, bocchi]",
                default_value="bocchi",
            )
        ],
    ).to_dict(),
)

from .goods_register import *  # noqa: F403

_matcher = on_alconna(
    Alconna(
        "商店",
        Option("--all", action=store_true),
        Subcommand("my-cost", help_text="我的金币"),
        Subcommand("my-props", help_text="我的道具"),
        Subcommand("buy", Args["name?", str]["num?", int], help_text="购买道具"),
        Subcommand("gold-list", Args["num?", int], help_text="金币排行"),
    ),
    priority=5,
    block=True,
)

_use_matcher = on_alconna(
    Alconna(
        "使用道具",
        Args["name?", str]["num?", int]["at_users?", MultiVar(At)],
    ),
    priority=5,
    block=True,
)

wrong_use_match = on_alconna(
    Alconna(
        "使用道具0",
    ),
    aliases={"使用道具1","使用道具2","使用道具3","使用道具4","使用道具5","使用道具6","使用道具7","使用道具8","使用道具9","使用道具10"},
    priority=5,
    block=True,
)

@wrong_use_match.handle()
async def _():
    await MessageUtils.build_message("道具后面要加空格的啊~").send(reply_to=True)

_matcher.shortcut(
    "我的金币",
    command="商店",
    arguments=["my-cost"],
    prefix=True,
)

_matcher.shortcut(
    "我的道具",
    command="商店",
    arguments=["my-props"],
    prefix=True,
)

_matcher.shortcut(
    "购买道具(?P<name>.*?)",
    command="商店",
    arguments=["buy", "{name}"],
    prefix=True,
)

_matcher.shortcut(
    "金币排行",
    command="商店",
    arguments=["gold-list"],
    prefix=True,
)

_matcher.shortcut(
    r"金币总排行",
    command="商店",
    arguments=["--all", "gold-list"],
    prefix=True,
)


@_matcher.assign("$main")
async def _(session: Uninfo, arparma: Arparma):
    image = await ShopManage.get_shop_image()
    logger.info("查看商店", arparma.header_result, session=session)
    await MessageUtils.build_message(image).send()


@_matcher.assign("my-cost")
async def _(session: Uninfo, arparma: Arparma):
    logger.info("查看金币", arparma.header_result, session=session)
    gold = await ShopManage.my_cost(
        session.user.id, PlatformUtils.get_platform(session)
    )
    await MessageUtils.build_message(f"你的当前余额: {gold}").send(reply_to=True)


@_matcher.assign("my-props")
async def _(session: Uninfo, arparma: Arparma, nickname: str = UserName()):
    logger.info("查看道具", arparma.header_result, session=session)
    if image := await ShopManage.my_props(
        session.user.id,
        nickname,
        PlatformUtils.get_platform(session),
    ):
        await MessageUtils.build_message(image.pic2bytes()).finish(reply_to=True)
    return await MessageUtils.build_message("你的道具为空捏...").send(reply_to=True)


@_matcher.assign("buy")
async def _(
    session: Uninfo,
    arparma: Arparma,
    name: Match[str],
    num: Query[int] = AlconnaQuery("num", 1),
):
    if not name.available:
        await MessageUtils.build_message(
            "请在指令后跟需要购买的道具名称或id..."
        ).finish(reply_to=True)
    logger.info(
        f"购买道具 {name}, 数量: {num}",
        arparma.header_result,
        session=session,
    )
    result = await ShopManage.buy_prop(session.user.id, name.result, num.result)
    await MessageUtils.build_message(result).send(reply_to=True)


@_use_matcher.handle()
async def _(
    bot: Bot,
    event: Event,
    message: UniMsg,
    session: Uninfo,
    arparma: Arparma,
    name: Match[str],
    num: Query[int] = AlconnaQuery("num", 1),
    at_users: Query[list[At]] = AlconnaQuery("at_users", []),
):
    if not name.available:
        await MessageUtils.build_message(
            "请在指令后跟需要使用的道具名称或id..."
        ).finish(reply_to=True)
    try:
        result = await ShopManage.use(
            bot, event, session, message, name.result, num.result, "", at_users.result
        )
        logger.info(
            f"使用道具 {name.result}, 数量: {num.result}",
            arparma.header_result,
            session=session,
        )
        if isinstance(result, str):
            await MessageUtils.build_message(result).send(reply_to=True)
        elif isinstance(result, UniMessage):
            await result.finish(reply_to=True)
    except GoodsNotFound:
        await MessageUtils.build_message(
            f"没有找到道具 {name.result} 或道具数量不足..."
        ).send(reply_to=True)
    except NotMeetUseConditionsException as e:
        if info := e.get_info():
            await MessageUtils.build_message(info).finish()  # type: ignore
        await MessageUtils.build_message(
            f"使用道具 {name.result} 的条件不满足..."
        ).send(reply_to=True)


@_matcher.assign("gold-list")
async def _(
    session: Uninfo, arparma: Arparma, num: Query[int] = AlconnaQuery("num", 10)
):
    if num.result > 50:
        await MessageUtils.build_message("排行榜人数不能超过50哦...").finish()
    gid = session.group.id if session.group else None
    if not arparma.find("all") and not gid:
        await MessageUtils.build_message(
            "私聊中无法查看 '金币排行'，请发送 '金币总排行'"
        ).finish()
    if arparma.find("all"):
        gid = None
    result = await gold_rank(session, gid, num.result)
    logger.info(
        "查看金币排行",
        arparma.header_result,
        session=session,
    )
    await MessageUtils.build_message(result).send(reply_to=True)
