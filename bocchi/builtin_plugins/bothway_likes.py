import asyncio
import random
import time
from nonebot import logger, on_notice
from nonebot.adapters import Bot,Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from bocchi.models.chat_history import ChatHistory
from bocchi.models.user_console import UserConsole
from bocchi.models.sign_user import SignUser
from bocchi.models.friend_user import FriendUser
from nonebot_plugin_uninfo import Uninfo
from bocchi.configs.utils import PluginExtraData
from nonebot.adapters.onebot.v11 import MessageSegment
from decimal import Decimal
__plugin_meta__ = PluginMetadata(
    name="双向点赞",
    description="相互点赞",
    usage="""
    指令：
        赞我/点赞 - 给自己点赞(仅限bot好友)
        给波奇点赞,会收到波奇的神秘馈赠~

    """,
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="0.0.2",
    ).to_dict(),
)

likes = on_alconna(
    Alconna("赞我"),
    aliases={"点赞"},
    priority=5,
    block=True,
)

# 用于跟踪正在等待统计的用户，存储格式：{user_id: {"likes": int, "start_time": float, "operator_nick": str}}
waiting_users = {}

TIMEOUT_SECONDS = 60  # 超时 1 分钟
async def send_thank_message(
    bot: Bot, 
    user_id: str, 
    operator_nick: str, 
    total_likes: int, 
    last_group_id: str | None
    ):
    """
    发送感谢消息并增加好感度
    :param bot: Bot对象
    :param user_id: 用户ID
    :param operator_nick: 用户昵称
    :param total_likes: 总点赞数
    :param last_group_id: 最后活跃的群聊ID
    """
    try:
        # 计算奖励
        add_gold = random.randint(1, 5 * total_likes)
        add_impression = round(random.uniform(0.02*total_likes, 0.2*total_likes), 2)
        
        if last_group_id:
            # 在群聊中发送消息
            try:
                message = MessageSegment.at(user_id) + f"谢谢你的 {total_likes} 个点赞～\n>///<小波奇送给你 {add_gold} 金币\n你和小波奇提升了 {add_impression:.2f} 好感度了呢"
                await bot.send_group_msg(group_id=last_group_id, message=message)
                # 增加好感度/金币
                sign_user = await SignUser.get_user(user_id=user_id)
                sign_user.impression = sign_user.impression + Decimal(str(add_impression))
                await sign_user.save()
                await UserConsole.add_gold(user_id, add_gold, "likes")
                logger.info(f"已在群聊 {last_group_id} 中向用户 {user_id} 发送感谢消息，增加好感度 {add_impression:.2f}，金币 {add_gold}")
            except Exception as e:
                logger.error(f"发送群聊消息失败: {e}")
        else:
            try:
                message = f"谢谢你的 {total_likes} 个点赞～\n小波奇送给你 {add_gold} 金币\n你和小波奇提升了 {add_impression:.2f} 好感度了呢"
                await bot.send_private_msg(user_id=int(user_id), message=message)
                # 增加好感度/金币
                sign_user = await SignUser.get_user(user_id=user_id)
                sign_user.impression = sign_user.impression + Decimal(str(add_impression))
                await sign_user.save()
                await UserConsole.add_gold(user_id, add_gold, "likes")
                logger.info(f"已向用户 {user_id} 发送私聊感谢消息，增加好感度 {add_impression:.2f}，金币 {add_gold}")
            except Exception as e:
                logger.error(f"发送私聊消息失败: {e}")
    except Exception as e:
        logger.error(f"发送感谢消息失败: {e}")

async def check_and_respond_likes(bot: Bot, user_id: str, operator_nick: str, last_group_id: str | None):
    """
    检查点赞数是否达到10个，如果达到则发送感谢消息
    :param bot: Bot对象
    :param user_id: 用户ID
    :param operator_nick: 用户昵称
    :param last_group_id: 最后活跃的群聊ID
    """
    try:
        if user_id not in waiting_users:
            return
            
        user_data = waiting_users[user_id]
        total_likes = user_data["likes"]
        
        # 只有点赞数达到10个时才发送消息并停止跟踪
        if total_likes >= 50:
            # 从等待列表中移除
            del waiting_users[user_id]
            await send_thank_message(bot, user_id, operator_nick, total_likes, last_group_id)
        else:
            logger.info(f"用户 {operator_nick}({user_id}) 当前点赞数: {total_likes}，继续等待到10个")
    except Exception as e:
        logger.error(f"检查点赞数失败: {e}")
        # 确保从等待列表中移除
        if user_id in waiting_users:
            del waiting_users[user_id]

async def timeout_cleanup(bot: Bot, user_id: str, operator_nick: str, last_group_id: str | None):
    """
    1分钟超时后清理用户数据并发送消息
    :param bot: Bot对象
    :param user_id: 用户ID
    :param operator_nick: 用户昵称
    :param last_group_id: 最后活跃的群聊ID
    """
    try:
        await asyncio.sleep(TIMEOUT_SECONDS)
        
        if user_id in waiting_users:
            user_data = waiting_users[user_id]
            total_likes = user_data["likes"]
            
            # 从等待列表中移除
            del waiting_users[user_id]
            
            # 发送超时感谢消息
            await send_thank_message(bot, user_id, operator_nick, total_likes, last_group_id)
            logger.info(f"用户 {operator_nick}({user_id}) 1分钟超时，发送 {total_likes} 个点赞感谢消息")
    except Exception as e:
        logger.error(f"超时清理失败: {e}")
        # 确保从等待列表中移除
        if user_id in waiting_users:
            del waiting_users[user_id]

async def get_user_last_active_group(user_id: str) -> str | None:
    """
    获取用户最后一次发言的群聊ID
    :param user_id: 用户ID
    :return: 群聊ID，如果是群组发言则返回群组ID，如果是私聊或没有发言则返回None
    """
    try:
        # 查询用户最后一次发言记录
        last_message = (
            await ChatHistory.filter(user_id=user_id)
            .order_by("-create_time")
            .first()
        )
        
        if last_message and last_message.group_id:
            # 如果最后一次发言是在群组中
            logger.info(f"用户 {user_id} 最后一次发言在群组 {last_message.group_id}")
            return last_message.group_id
        else:
            # 如果最后一次发言是私聊或没有发言记录
            logger.info(f"用户 {user_id} 最后一次发言是私聊或没有发言记录")
            return None
    except Exception as e:
        logger.error(f"查询用户最后发言群聊失败: {e}")
        return None

async def dian_likes(bot: Bot, user_id:int):
    """
    核心函数，给指定用户点赞
    :param bot: Bot对象
    :param user_id: 用户ID
    :return: 点赞次数
    """
    count = 0
    try:
        for _ in range(5):
            await bot.send_like(user_id=user_id, times=10)  
            count += 10
            logger.info(f"点赞成功，当前点赞次数：{count}")
    except Exception as e:
        logger.error(f"点赞失败: {e}")
    return count

@likes.handle()
async def _(bot: Bot, session: Uninfo):
    """
    处理点赞事件
    :param bot: Bot对象
    :param session: Uninfo对象
    :return: None
    """
    user_id = str(session.user.id)
    
    # 检查是否为好友关系
    friend_user = await FriendUser.get_or_none(user_id=user_id)
    if not friend_user:
        await likes.finish("那个...小波奇只敢给好友点赞啦...Σ( ° △ °|||)︴")
    
    count = await dian_likes(bot, int(session.user.id))
    if count != 0:
        await likes.send(f"已经给你点了{count}个赞!\n >///<小波奇希望你也能给她点赞哦~")
    else:
        await likes.finish(f"今天给你点过了哦...不要太贪心了啊...(*￣︶￣)σ")

def is_profile_like(event: Event) -> bool:
    return getattr(event, "notice_type") == "notify" and getattr(event, "sub_type") == "profile_like"

profile_like = on_notice(
    priority=5,
    rule=is_profile_like
)
@profile_like.handle()
async def handle_profile_like(bot: Bot, event: Event):
    """处理个人资料点赞事件，只有点赞到10个时才停止跟踪并输出，1分钟超时"""
    try:
        user_id = getattr(event, "operator_id")
        times = getattr(event, "times")
        operator_nick = getattr(event, "operator_nick")
        # 查找用户最后活跃的群聊
        last_group_id = await get_user_last_active_group(user_id)
        
        # 累加点赞数
        if user_id in waiting_users:
            waiting_users[user_id]["likes"] += times
        else:
            # 新用户开始跟踪
            waiting_users[user_id] = {
                "likes": times,
                "start_time": time.time(),
                "operator_nick": operator_nick
            }
            # 启动1分钟超时任务
            asyncio.create_task(timeout_cleanup(bot, user_id, operator_nick, last_group_id))
            logger.info(f"用户 {operator_nick}({user_id}) 开始点赞，当前总数: {times}")
        
        logger.info(f"用户 {operator_nick}({user_id}) 点赞 {times} 次，当前总数: {waiting_users[user_id]['likes']}")
        
        # 检查是否达到10个点赞
        await check_and_respond_likes(bot, user_id, operator_nick, last_group_id)
                        
    except Exception as e:
        logger.error(f"处理点赞事件失败: {e}")