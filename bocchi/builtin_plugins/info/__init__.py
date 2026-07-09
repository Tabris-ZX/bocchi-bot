from arclet.alconna import Option
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, At, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo
from playwright.async_api import TimeoutError
from bocchi.models.user_console import UserConsole
from bocchi.utils.enum import GoldHandle
from bocchi.configs.utils import Command, PluginExtraData
from bocchi.models.group_member_info import GroupInfoUser
from bocchi.services.log import logger
from bocchi.utils.depends import UserName
from bocchi.utils.message import MessageUtils
from .my_info import get_user_info, update_info

__plugin_meta__ = PluginMetadata(
    name="查看信息",
    description="查看个人信息",
    usage="""
    查看个人/群组信息
    指令：
        我的信息 ?[at] - 查看某人的信息
        更新/修改信息 ?头衔[str] 种族[str] 职业[str] 简介[str] - 更新某人的信息
        
    示例：    
        更新信息 头衔 abc 种族 123
        修改信息 简介 qwertyuiop
        
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", commands=[Command(command="我的信息")]
    ).to_dict(),
)

my_info_matcher = on_alconna(Alconna("我的信息", Args["at_user?", At]), priority=5, block=True)

update_matcher = on_alconna(
    Alconna("更新信息",
        Option("头衔", Args["title", str,""]),
        Option("种族", Args["race", str,""]),
        Option("职业", Args["occupation", str,""]),
        Option("简介", Args["description", str,""])
    ),
    aliases={"修改信息"},
    priority=5,
    block=True
)

@my_info_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    at_user: Match[At],
    nickname: str = UserName(),
):
    user_id = session.user.id
    if at_user.available and session.group:
        user_id = at_user.result.target
        if user := await GroupInfoUser.get_or_none(
            user_id=user_id, group_id=session.group.id
        ):
            nickname = user.user_name
        else:
            nickname = user_id
    try:
        result = await get_user_info(
            session, user_id, session.group.id if session.group else None, nickname
        )
        await MessageUtils.build_message(result).send(at_sender=True)
        logger.info("获取用户信息", arparma.header_result, session=session)
    except TimeoutError as e:
        logger.error("获取用户信息超时", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("获取用户信息超时...").finish(reply_to=True)
    except Exception as e:
        logger.error("获取用户信息失败", arparma.header_result, session=session, e=e)
        await MessageUtils.build_message("获取用户信息失败...").finish(reply_to=True)

@update_matcher.handle()
async def _(
        session: Uninfo,
        title: Match[str],
        race: Match[str],
        occupation: Match[str],
        description: Match[str],
):
    from bocchi.services.log import logger
    logger.info(
        f"收到修改信息请求: title={title.result if title.available else ''}, "
        f"race={race.result if race.available else ''}, "
        f"occupation={occupation.result if occupation.available else ''}, "
        f"description={description.result if description.available else ''}",
        "INFO",
    )
    
    user = await UserConsole.get_user(session.user.id)
    logger.info(f"用户金币余额: {user.gold}", "INFO")
    
    if user.gold<91:
        await MessageUtils.build_message("金币不足！需要91金币才能修改信息。").finish()
    updates = {}
    if title.available and title.result != "":
        updates["title"] = title.result
        logger.info(f"设置头衔: {title}", "INFO")
    if race.available and race.result != "":
        updates["race"] = race.result
        logger.info(f"设置种族: {race}", "INFO")
    if occupation.available and occupation.result != "":
        updates["occupation"] = occupation.result
        logger.info(f"设置职业: {occupation}", "INFO")
    if description.available and description.result != "":
        updates["description"] = description.result
        logger.info(f"设置简介: {description}", "INFO")
    
    logger.info(f"更新参数: {updates}", "INFO")
    if not updates:
        await MessageUtils.build_message("未提供任何修改项。").finish()
        return
    success=await update_info(user_id=user.user_id, **updates)
    if success:
        await UserConsole.reduce_gold(user.user_id, 91, GoldHandle.BUY, 'info')
        await MessageUtils.build_message("修改成功！").finish()
    else:
        await MessageUtils.build_message("指令格式错误，修改失败！").finish()
