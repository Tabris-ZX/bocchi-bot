import random
from bocchi.utils.enum import GoldHandle
from bocchi.models.user_console import UserConsole
from bocchi.utils.decorator.shop import shop_register, NotMeetUseConditionsException

@shop_register(
    name="神秘药水",
    price=999999,
    des="鬼知道会有什么效果，要不试试？",
    partition="娱乐道具",
    icon="mysterious_potion.png",
)
async def _(user_id: str):
    await UserConsole.add_gold(
        user_id,
        114514,
        "shop",
    )
    return "使用道具神秘药水成功！你滴金币+114514！"


@shop_register(
    name="盲盒",
    price=100,
    des="打开盲盒，可能获得不同奖励，也可能失去金币！风险与机遇并存~",
    partition="娱乐道具",
    icon="mysterious_potion.png",
)
async def _(user_id: str):
    open_chance = random.randint(1, 100)
    
    if open_chance < 40:
        if open_chance < 25:
            lost_gold = random.randint(1, 100)
            await UserConsole.reduce_gold(
                user_id,
                lost_gold,
                GoldHandle.BUY,
                "shop",
            )
            return f"盲盒打开了...哎呀！你失去了 {lost_gold} 金币！💸"
        else:
            gained_gold = random.randint(1, 200)
            await UserConsole.add_gold(
                user_id,
                gained_gold,
                "shop",
            )
            return f"盲盒打开了...还不错！你获得了 {gained_gold} 金币！💰"
    
    elif open_chance < 65:
        from bocchi.plugins.setu.send_setu import SetuManage
        setu_list = await SetuManage.get_setu(num=1, local = True)
        if isinstance(setu_list, str):
            return "盲盒打开了...获得了一张色图!🎁...但是发生了一些意外,色图没发出来啦~"
        for setu in setu_list:
            await setu.send()
        return "盲盒打开了...获得了一张色图!🎁"

    elif open_chance < 90:
        gift_chance = random.randint(1, 100)
        if gift_chance < 70:
            await UserConsole.add_props_by_name(
                user_id,
                "好感度双倍加持卡Ⅰ",
                1,
            )
            return f"盲盒打开了...还不错！你获得了 好感度双倍加持卡Ⅰ！🎁"
        elif gift_chance < 90:
            await UserConsole.add_props_by_name(
                user_id,
                "好感度双倍加持卡Ⅱ",
                1,
            )
            return f"盲盒打开了...哇！你获得了 好感度双倍加持卡Ⅱ！🎁"
        else:
            await UserConsole.add_props_by_name(
                user_id,
                "好感度双倍加持卡Ⅲ",
                1,
            )
            return f"盲盒打开了...哇噻！你获得了 好感度双倍加持卡Ⅲ！🎁"

    elif open_chance < 98:
        return "盲盒打开了...什么都没有！🤷‍♂️"

    else:
        await UserConsole.add_gold(
            user_id,
            1888,
            "shop",
        )
        return f"盲盒打开了...🎊🎊🎊 恭喜你中了大奖！获得 1888 金币！🎊🎊🎊"

@shop_register.before_handle(name="盲盒")
async def _(user_id: str):
    user = await UserConsole.get_user(user_id)
    if user.gold < 200:
        raise NotMeetUseConditionsException("你的金币太少，建议先攒够200金币再玩盲盒，避免破产！⚠️")
