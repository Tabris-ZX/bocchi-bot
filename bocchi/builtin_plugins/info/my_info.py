from datetime import datetime, timedelta
import random
import json

from nonebot_plugin_uninfo import Uninfo
from tortoise.expressions import RawSQL
from tortoise.functions import Count

from bocchi import ui
from bocchi.models.chat_history import ChatHistory
from bocchi.models.level_user import LevelUser
from bocchi.models.sign_user import SignUser
from bocchi.models.statistics import Statistics
from bocchi.models.user_console import UserConsole
from bocchi.utils.platform import PlatformUtils
from bocchi.configs.path_config import DATA_PATH
import aiofiles
from bocchi.services.log import logger

USER_PATH = DATA_PATH / "my_info"
RACE = [
    "龙族",
    "魅魔",
    "森林精灵",
    "血精灵",
    "暗夜精灵",
    "狗头人",
    "狼人",
    "猫人",
    "猪头人",
    "骷髅",
    "僵尸",
    "虫族",
    "人类",
    "天使",
    "恶魔",
    "甲壳虫",
    "猎猫",
    "人鱼",
    "哥布林",
    "地精",
    "泰坦",
    "矮人",
    "山巨人",
    "石巨人",
]

SEX = ["男", "女"]

OCC = [
    "猎人",
    "战士",
    "魔法师",
    "狂战士",
    "魔战士",
    "盗贼",
    "术士",
    "牧师",
    "骑士",
    "刺客",
    "游侠",
    "召唤师",
    "圣骑士",
    "魔使",
    "龙骑士",
    "赏金猎手",
    "吟游诗人",
    "德鲁伊",
    "祭司",
    "符文师",
    "狂暴术士",
    "萨满",
    "裁决者",
    "角斗士",
]

lik2level = {
    5120: 9,
    2560: 8,
    1280: 7,
    640: 6,
    320: 5,
    160: 4,
    80: 3,
    40: 2,
    20: 1,
    0: 0,
}


def get_level(impression: float) -> int:
    """获取好感度等级"""
    return next((level for imp, level in lik2level.items() if impression >= imp), 0)


async def get_chat_history(
    user_id: str, group_id: str | None
) -> tuple[list[str], list[int]]:
    """获取用户聊天记录

    参数:
        user_id: 用户id
        group_id: 群id

    返回:
        tuple[list[str], list[int]]: 日期列表, 次数列表

    """
    now = datetime.now()
    filter_date = now - timedelta(days=7)
    date_list = (
        await ChatHistory.filter(
            user_id=user_id, group_id=group_id, create_time__gte=filter_date
        )
        .annotate(date=RawSQL("DATE(create_time)"), count=Count("id"))
        .group_by("date")
        .values("date", "count")
    )
    chart_date: list[str] = []
    count_list: list[int] = []
    date2cnt = {str(item["date"]): item["count"] for item in date_list}
    current_date = now.date()
    for _ in range(7):
        date_str = str(current_date)
        count_list.append(date2cnt.get(date_str, 0))
        chart_date.append(date_str[5:])
        current_date -= timedelta(days=1)
    chart_date.reverse()
    count_list.reverse()
    return chart_date, count_list


async def get_user_info(
        session: Uninfo, user_id: str, group_id: str | None, nickname: str
) -> bytes:
    """获取用户个人信息"""

    platform = PlatformUtils.get_platform(session) or "qq"
    ava_url = PlatformUtils.get_user_avatar_url(user_id, platform, session.self_id)
    user = await UserConsole.get_user(user_id, platform)
    level = await LevelUser.get_user_level(user_id, group_id)
    sign_level = 0
    if sign_user := await SignUser.get_or_none(user_id=user_id):
        sign_level = get_level(float(sign_user.impression))
    chat_count = await ChatHistory.filter(user_id=user_id, group_id=group_id).count()
    stat_count = await Statistics.filter(user_id=user_id, group_id=group_id).count()
    select_index = ["" for _ in range(9)]
    select_index[sign_level] = "select"
    uid = f"{user.uid}".rjust(8, "0")
    uid = f"{uid[:4]} {uid[4:]}"

    now = datetime.now()
    weather = "moon" if now.hour < 6 or now.hour > 19 else "sun"
    chart_date, count_list = await get_chat_history(user_id, group_id)

    profile_data = {
        "page": {
            "date": str(now.date()),
            "weather_icon_name": weather,
        },
        "info": {  # ⚠️ 注意：这里和 template.json 对齐
            "avatar_url": ava_url,
            "nickname": nickname,
            "title": "勇 者",
            "race": random.choice(RACE)+"(随机)",
            # "sex": random.choice(SEX),
            "occupation": random.choice(OCC)+"(随机)",
            "uid": uid,
            "description": (
                "你还没有个人简介捏,快去设置吧!"
            ),
        },
        "stats": {
            "gold": user.gold,
            "prop_count": len(user.props),
            "call_count": stat_count,
            "chat_count": chat_count,
        },
        "favorability": {
            "level": sign_level,
            "selected_indices": select_index,
        },
        "permission_level": level,
        "chart": {
            "labels": chart_date,
            "data": count_list,
        },
    }

    appoint = USER_PATH / "appointed" / f"{user_id}.json"
    if appoint.exists():
        with appoint.open("r", encoding="utf-8") as f:
            update = json.load(f)
            # ⚠️ 修改点：update 文件中是 {"info": {...}} 结构
            if "info" in update:
                for key, value in update["info"].items():
                    if value != "":
                        profile_data["info"][key] = value

    return await ui.render_template("pages/builtin/my_info", data=profile_data)


async def update_info(user_id: str, **update) -> bool:
    """更新用户信息"""
    user_info = USER_PATH / "appointed" / f"{user_id}.json"
    user_info.parent.mkdir(parents=True, exist_ok=True)

    temp = {}
    if user_info.exists():
        async with aiofiles.open(user_info, mode='r', encoding='utf-8') as f:
            try:
                temp = json.loads(await f.read())
            except json.decoder.JSONDecodeError:
                logger.error("修改信息格式错误")
                return False
    else:
        create = USER_PATH / "template.json"
        async with aiofiles.open(create, mode='r', encoding='utf-8') as f:
            try:
                temp = json.loads(await f.read())
            except json.decoder.JSONDecodeError:
                logger.error("修改信息格式错误")
                return False

    # ⚠️ 修改点：update 的内容要写入 temp["info"] 而不是 temp 本身
    if "info" not in temp:
        temp["info"] = {}

    temp["info"].update(update)  # 只更新 info 里面的字段

    async with aiofiles.open(user_info, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(temp, ensure_ascii=False, indent=4))
        return True
