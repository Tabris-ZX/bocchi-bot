import nonebot
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_apscheduler import scheduler

from bocchi.configs.utils import PluginExtraData, Task
from bocchi.services.log import logger
from bocchi.utils.common_utils import CommonUtils
from bocchi.utils.enum import PluginType
from bocchi.utils.message import MessageUtils
from bocchi.utils.platform import broadcast_group

__plugin_meta__ = PluginMetadata(
    name="今日算竞",
    description="今日oj算法比赛",
    usage="",
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="0.1.0",
        plugin_type=PluginType.HIDDEN,
        tasks=[
            Task(
                module="today_algo",
                name="今日算竞",
                create_status=False,
                default_status=False,
            )
        ],
    ).to_dict(),
)

driver = nonebot.get_driver()

async def check(bot: Bot, group_id: str) -> bool:
    return not await CommonUtils.task_is_block(bot, "today_algo", group_id)


@scheduler.scheduled_job(
    "cron",
    hour=6,
    minute=1,
)
async def _():
    from bocchi.plugins.nonebot_plugin_algo.query import Query
    
    message = MessageUtils.build_message(await Query.ans_today_contests())
    await broadcast_group(message, log_cmd="被动今日算竞", check_func=check)
    logger.info("每日算竞发送...")