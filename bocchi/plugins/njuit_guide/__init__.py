from arclet.alconna import Args, Option
from nonebot import get_bot
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_uninfo import Uninfo

from bocchi.utils.enum import GoldHandle

from bocchi.models.user_console import UserConsole
from .data_source import DataSource
from .electricity import Electricity
from bocchi.configs.utils import BaseBlock, Command, PluginExtraData
from bocchi.services.log import logger
from bocchi.utils.message import MessageUtils
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot.adapters.onebot.v11 import MessageSegment
from bocchi.configs.path_config import DATA_PATH
from bocchi.configs.utils import PluginExtraData
from bocchi.services.log import logger
from bocchi.utils.message import MessageUtils

from nonebot_plugin_apscheduler import scheduler
from bocchi.configs.utils import PluginExtraData, Task
from bocchi.services.log import logger
from .data_source import DataSource
from bocchi.utils.common_utils import CommonUtils
from .config import njuit_config as conf
from .model import NjuitStu


__plugin_meta__ = PluginMetadata(
    name="南工指北",
    description="旨在为南工院学生提供一些便捷辅助",
    usage="""
    南工新生: 获取新生指南pdf
    南工地图: 南工院彩绘地图
    南工宿舍/宿舍号码:获取宿舍电费充值号码(id)
    (暂时移除)今日校果 ?[帖子数=10] ?[评论数=10]: 查询最新n条校果论坛帖子
    (暂时移除)校果热榜: 查询校果论坛热榜帖子
    南工绑定/绑定南工 ?dorm [宿舍号] ?class [班级名]: 私聊绑定qq账户和你的宿舍/班级
    电费查询: 查询已绑定宿舍的电费余额
    电费推送 开/关: 开启/关闭每日电费推送和预警邮件
    
    示例: 
    南工绑定 dorm 114514
    南工绑定 class 班级1919
    电费推送 开

    """.strip(),
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="0.5.2",
        tasks=[
            Task(module="today_xiaoguo", name="今日校果"), 
            Task(module="today_bill_push", name="今日电费提醒")
        ],
    ).to_dict(),
)

FILE_PATH = DATA_PATH / "njuit_guide"


fm_matcher = on_alconna(
    Alconna("南工新生"),
    priority=5,
    block=True,
)
map_matcher = on_alconna(
    Alconna("南工地图"),
    priority=5,
    block=True,
)
dorm_id_matcher = on_alconna(
    Alconna("南工宿舍"),
    aliases={"宿舍id","宿舍号码"},
    priority=5,
    block=True,
)
bind_matcher = on_alconna(
    Alconna(
        "南工绑定",
        Option("class", Args["class_name", str, ""]),
        Option("dorm", Args["dorm_id", str, ""]),
    ),
    aliases={"绑定南工"},
    priority=5,
    block=True,
)

query_matcher = on_alconna(
    Alconna("电费查询"),
    aliases={"查询电费","宿舍电费"},
    priority=5,
    block=True,
)

push_matcher = on_alconna(
    Alconna(
        "电费推送",
        Args["action", str],
    ),
    priority=5,
    block=True,
)

xg_latest_matcher = on_alconna(
    Alconna(
        "今日校果",
        Args["tp_num?", int, conf.topic_num],
        Args["cmt_num?", int, conf.comment_num],
    ),
    priority=5,
    block=True,
)
xg_hot_matcher = on_alconna(
    Alconna("校果热榜"),
    priority=5,
    block=True,
)

@xg_latest_matcher.handle()
async def _(tp_num: int, cmt_num: int):
    img = await DataSource.get_topics(tp_num=tp_num, cmt_num=cmt_num,url=conf.xg_latest_url)
    if not img == None:
        await MessageUtils.build_message(img).send()
    else:
        await MessageUtils.build_message("发生了一些错误,肯定不是波奇的问题!").send()
        logger.error("图片获取失败")


@xg_hot_matcher.handle()
async def handle_xg_hot():
    img = await DataSource.get_topics(tp_num=conf.topic_num,cmt_num=conf.comment_num,url=conf.xg_hot_url)
    if not img == None:
        await MessageUtils.build_message(img).send()
    else:
        await MessageUtils.build_message("发生了一些错误,肯定不是波奇的问题!").send()
        logger.error("图片获取失败")


@fm_matcher.handle()
async def handle_fm_match():
    pdf_path = FILE_PATH / "freshman.pdf"
    msg = await DataSource.send_file(pdf_path, "南工院新生宝典")
    await fm_matcher.finish(msg)


@map_matcher.handle()
async def handle_send_image():
    # 构建完整图片路径
    map_path = FILE_PATH / "map.png"
    await MessageUtils.build_message(map_path).send()


@dorm_id_matcher.handle()
async def handle_send_ow():
    dorm_id_path = FILE_PATH/"dorm_id.png"
    await MessageUtils.build_message(dorm_id_path).send()


@bind_matcher.handle()
async def handle_bind(session: Uninfo, class_name: str = "", dorm_id: str = ""):
    # 检查是否提供了必要的参数
    if not class_name and not dorm_id:
        await MessageUtils.build_message(
            "请提供班级或宿舍信息！\n使用教程:请发送'波奇帮助91'"
        ).send(reply_to=True)
        return
    
    bind = await Electricity.bind_info(
        user_id=session.user.id, class_name=class_name, dorm_id=dorm_id
    )
    logger.info(
        f"绑定结果: 用户ID: {session.user.id}, 班级: {class_name}, 宿舍: {dorm_id}"
    )
    if bind:
        await MessageUtils.build_message("✅ 绑定成功！(宿舍绑定后,电费推送自动开启)").send(reply_to=True)
    else:
        await MessageUtils.build_message("❌ 绑定失败,可能是宿舍或是班级写错了或者学校网络炸了,但肯定不是波奇的问题!").send(reply_to=True)


@query_matcher.handle()
async def handle_query(session: Uninfo):
    msg = await Electricity.query_balance(session.user.id)
    await MessageUtils.build_message(msg).send(reply_to=True)


@push_matcher.handle()
async def handle_push_setting(session: Uninfo, action: str):
    """处理电费推送设置"""
    
    user_id = session.user.id
    
    # 检查用户是否已绑定宿舍
    user_data = await NjuitStu.get_data(user_id)
    if not user_data or not user_data.dorm_id:
        dorm_id_path = FILE_PATH/"dorm_id.png"
        await MessageUtils.build_message(["先绑定宿舍信息才能开启电费推送哦！\n私聊小波奇发送\n账号绑定  dorm  宿舍id\n来绑定宿舍吧~",dorm_id_path]).send(reply_to=True)
        return
    
    if action in ["开启", "开", "on"]:
        success = await NjuitStu.update_push_status(user_id, True)
        if success:
            await MessageUtils.build_message("✅ 电费推送已开启！每天早上8点会收到电费余额提醒").send(reply_to=True)
        else:
            await MessageUtils.build_message("❌ 开启失败，请稍后重试").send(reply_to=True)
    elif action in ["关闭", "关", "off"]:
        success = await NjuitStu.update_push_status(user_id, False)
        if success:
            await MessageUtils.build_message("✅ 电费推送已关闭").send(reply_to=True)
        else:
            await MessageUtils.build_message("❌ 关闭失败，请稍后重试").send(reply_to=True)
    else:
        await MessageUtils.build_message("请使用：电费推送 开启/开/on 关闭/关/off\n别的格式小波奇不认哦~").send(reply_to=True)


# 每日定时任务
# async def xg_check(bot: Bot, group_id: str) -> bool:
#     return not await CommonUtils.task_is_block(bot, "today_xiaoguo", group_id)

# @scheduler.scheduled_job(
#     "cron",
#     hour=12,
#     minute=0,
# )
# async def send_daily_xg():
#     try:
#         img = await DataSource.get_topics(tp_num=conf.topic_num,cmt_num=conf.comment_num,url=conf.xg_latest_url)
#         if img == None:
#             logger.error("图片获取失败")
#             return
#         msg = MessageUtils.build_message(img)
#         await broadcast_group(
#             msg,
#             log_cmd="今日校果",  # 修改日志标识
#             check_func=xg_check,
#         )
#         logger.info("每日校果提醒发送成功")
#     except Exception as e:
#         logger.error(f"发送每日校果提醒失败: {e}")
   
async def push_check(bot: Bot, group_id: str) -> bool:
    """检查群组是否应该接收电费推送"""
    # 检查任务是否被阻止
    if await CommonUtils.task_is_block(bot, "today_bill_push", group_id):
        return False
    try:
        # 获取群成员列表
        group_members = await bot.get_group_member_list(group_id=int(group_id))
        member_ids = [str(member['user_id']) for member in group_members]
        
        # 检查是否有开启推送的用户在群中
        users_with_push = await NjuitStu.filter(push=True, user_id__in=member_ids).all()
        return len(users_with_push) > 0
    except Exception as e:
        logger.error(f"检查群组 {group_id} 推送权限失败: {e}")
        return False


@scheduler.scheduled_job(
    "cron",
    hour=21,
    minute=0,
)
async def send_daily_electricity_reminder():
    """每天发送电费提醒"""
    try:    
        bot = get_bot()
        
        # 第一步：检查电费不足用户并发送邮件提醒
        logger.info("开始检查电费不足用户并发送邮件提醒")
        email_sent_count = await Electricity.check_low_balance_and_send_email(threshold=15.0)
        logger.info(f"电费不足邮件提醒发送完成，共发送 {email_sent_count} 封邮件")
        
        # 第二步：获取所有开启推送的用户
        users = await NjuitStu.filter(push=True).all()
        if not users:
            logger.info("没有用户开启电费推送")
            return
            
        # 第三步：获取所有群组并发送群组提醒
        groups = await bot.get_group_list()
        sent_count = 0
        
        for group in groups:
            group_id = str(group['group_id'])
            
            # 检查群组是否应该接收推送
            if not await push_check(bot, group_id):
                continue
            
            # 为这个群生成消息
            message_content = await Electricity.get_daily_electricity_reminder_for_group(group_id)
            if message_content is None:
                continue
            try:
                msg = MessageSegment.image(message_content)
                await bot.send_group_msg(group_id=int(group_id), message=msg)
                sent_count += 1
                logger.info(f"电费提醒已发送到群 {group_id}")
            except Exception as e:
                logger.error(f"发送电费提醒到群 {group_id} 失败: {e}")
        
        logger.info(f"每日电费提醒发送完成，邮件: {email_sent_count} 封，群组: {sent_count} 个")
    except Exception as e:
        logger.error(f"发送每日电费提醒失败: {e}")
