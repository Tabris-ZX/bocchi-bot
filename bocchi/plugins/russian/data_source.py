import contextlib
import random
import time
from datetime import datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from nonebot.adapters import Bot
from nonebot_plugin_alconna import At, UniMessage
from nonebot_plugin_apscheduler import scheduler
from pydantic import BaseModel
from bocchi.configs.config import BotConfig, Config
from bocchi.models.group_member_info import GroupInfoUser
from bocchi.models.user_console import UserConsole
from bocchi.utils.enum import GoldHandle
from bocchi.utils.exception import InsufficientGold
from bocchi.utils.image_utils import BuildImage, BuildMat, MatType, text2image
from bocchi.utils.message import MessageUtils
from bocchi.utils.platform import PlatformUtils

from .model import RussianUser

base_config = Config.get("russian")


class Russian(BaseModel):
    at_user: str | None
    """指定决斗对象"""
    player1: tuple[str, str]
    """玩家1id, 昵称"""
    player2: tuple[str, str] | None = None
    """玩家2id, 昵称"""
    money: int
    """金额"""
    bullet_num: int
    """子弹数"""
    bullet_arr: list[int] = []
    """子弹排列"""
    bullet_index: int = 0
    """当前子弹下标"""
    current_turn: str = ""
    """当前回合的用户"""
    time: float = time.time()
    """创建时间"""
    win_user: str | None = None
    """胜利者"""


class RussianManage:
    def __init__(self) -> None:
        self._data: dict[str, Russian] = {}

    def __check_is_timeout(self, group_id: str) -> bool:
        """检查决斗是否超时

        参数:
            group_id: 群组id

        返回:
            bool: 是否超时
        """
        if russian := self._data.get(group_id):
            if russian.time + 30 < time.time():
                return True
        return False

    def __random_bullet(self, num: int) -> list[int]:
        """随机排列子弹

        参数:
            num: 子弹数量

        返回:
            list[int]: 子弹排列数组
        """
        bullet_list = [0, 0, 0, 0, 0, 0, 0]
        for i in random.sample([0, 1, 2, 3, 4, 5, 6], num):
            bullet_list[i] = 1
        return bullet_list

    def __remove_job(self, group_id: str):
        """移除定时任务

        参数:
            group_id: 群组id
        """
        with contextlib.suppress(JobLookupError):
            scheduler.remove_job(f"russian_job_{group_id}")

    def __build_job(
        self, bot: Bot, group_id: str, is_add: bool = False, platform: str | None = None
    ):
        """移除定时任务和构建新定时任务

        参数:
            bot: Bot
            group_id: 群组id
            is_add: 是否添加新定时任务.
            platform: 平台
        """
        self.__remove_job(group_id)
        if is_add and not PlatformUtils.is_qbot(bot):
            date = datetime.now() + timedelta(seconds=31)
            scheduler.add_job(
                self.__auto_end_game,
                "date",
                run_date=date.replace(microsecond=0),
                id=f"russian_job_{group_id}",
                args=[bot, group_id, platform],
            )

    async def __auto_end_game(self, bot: Bot, group_id: str, platform: str):
        """自动结束对决

        参数:
            bot: Bot
            group_id: 群组id
            platform: 平台
        """
        result = await self.settlement(group_id, None, platform)
        if result:
            await PlatformUtils.send_message(bot, None, group_id, result)

    async def add_russian(self, bot: Bot, group_id: str, rus: Russian) -> UniMessage:
        """添加决斗

        参数:
            bot: Bot
            group_id: 群组id
            rus: Russian

        返回:
            UniMessage: 返回消息
        """
        if russian := self._data.get(group_id):
            if russian.time + 30 < time.time():
                if not russian.player2:
                    return MessageUtils.build_message(
                        f"现在是 {russian.player1[1]} 发起的对决,"
                        f" 请接受对决或等待决斗超时..."
                    )
                else:
                    return MessageUtils.build_message(
                        f"{russian.player1[1]} 和 {russian.player2[1]}的对决还未结束！"
                    )
            return MessageUtils.build_message(
                f"现在是 {russian.player1[1]} 发起的对决\n请等待比赛结束后再开始下一轮."
            )
        max_money = base_config.get("MAX_RUSSIAN_BET_GOLD")
        if rus.money > max_money:
            return MessageUtils.build_message(f"太多了！单次金额不能超过{max_money}！")
        user = await UserConsole.get_user(rus.player1[0])
        if user.gold < rus.money:
            return MessageUtils.build_message(
                "你没有足够的钱支撑起这场挑战，如果需要指定金额，"
                "可以输入 装弹 1(子弹数) 100(金额)"
            )
        rus.bullet_arr = self.__random_bullet(rus.bullet_num)
        self._data[group_id] = rus
        message_list: list[str | At] = []
        if rus.at_user:
            user = await GroupInfoUser.get_or_none(
                user_id=rus.at_user, group_id=group_id
            )
            message_list = [
                f"{rus.player1[1]} 向",
                At(flag="user", target=rus.at_user),
                f"发起了决斗！请 {user.user_name if user else rus.at_user}",
                " 在30秒内回复‘接受’ or ‘拒绝’，超时此次决斗作废！",
            ]
        else:
            message_list = [
                "其他人可以发送'接受'来接受决斗",
                "若30秒内无人接受挑战则此次对决作废"
                "【首次游玩请at我发送 ’帮助俄罗斯轮盘‘ 来查看命令】"
            ]
        result = (
            "咔 " * rus.bullet_num
            + f"装填完毕\n挑战金额：{rus.money}\n"
            + f"第一枪的概率为：{float(rus.bullet_num) / 7.0 * 100:.2f}%\n"
        )

        message_list.insert(0, result)
        self.__build_job(bot, group_id, True)
        return MessageUtils.build_message(message_list)  # type: ignore

    async def accept(
        self, bot: Bot, group_id: str, user_id: str, uname: str
    ) -> UniMessage:
        """接受对决

        参数:
            bot: Bot
            group_id: 群组id
            user_id: 用户id
            uname: 用户名称

        返回:
            Text | MessageFactory: 返回消息
        """
        if russian := self._data.get(group_id):
            if russian.at_user and russian.at_user != user_id:
                return MessageUtils.build_message("又不是找你决斗，你接受什么啊！气！")
            if russian.player2:
                return MessageUtils.build_message(
                    "当前决斗已被其他玩家接受！请等待下局对决！"
                )
            if russian.player1[0] == user_id:
                return MessageUtils.build_message("你发起的对决，你接受什么啊！气！")
            user = await UserConsole.get_user(user_id)
            if user.gold < russian.money:
                return MessageUtils.build_message("你没有足够的钱来接受这场挑战...")
            russian.player2 = (user_id, uname)
            russian.current_turn = russian.player1[0]
            self.__build_job(bot, group_id, True)
            return MessageUtils.build_message(
                [
                    "决斗已经开始！请",
                    At(flag="user", target=russian.player1[0]),
                    "先开枪！(开他/开我)",
                ]
            )
        return MessageUtils.build_message(
            "目前没有进行的决斗，请发送 装弹 开启决斗吧！"
        )

    def refuse(self, group_id: str, user_id: str, uname: str) -> UniMessage:
        """拒绝决斗

        参数:
            group_id: 群组id
            user_id: 用户id
            uname: 用户名称

        返回:
            Text | MessageFactory: 返回消息
        """
        if russian := self._data.get(group_id):
            if russian.at_user:
                if russian.at_user != user_id:
                    return MessageUtils.build_message(
                        "又不是找你决斗，你拒绝什么啊！气！"
                    )
                del self._data[group_id]
                self.__remove_job(group_id)
                return MessageUtils.build_message(
                    [
                        At(flag="user", target=russian.player1[0]),
                        f"{uname}拒绝了你的对决！",
                    ]
                )
            return MessageUtils.build_message("当前决斗并没有指定对手，无法拒绝哦！")
        return MessageUtils.build_message(
            "目前没有进行的决斗，请发送 装弹 开启决斗吧！"
        )

    async def shoot(
            self,
            bot: Bot,
            group_id: str,
            user_id: str,
            uname: str,
            platform: str,
            shoot_type: str = "opponent"  # 修改点1：新增shoot_type参数，默认打对方
    ) -> tuple[UniMessage, UniMessage | None]:
        """开枪

        参数:
            bot: Bot
            group_id: 群组id
            user_id: 用户id
            uname: 用户名称
            platform: 平台
            shoot_type: 射击类型 (self/opponent)  # 修改点2：添加参数说明

        返回:
            tuple[UniMessage, UniMessage | None]: 返回消息和结算消息
        """
        if russian := self._data.get(group_id):
            if not russian.player2:
                return (
                    MessageUtils.build_message("当前还没有玩家接受对决，无法开枪..."),
                    None,
                )

            # 修改点3：优化非玩家提示
            if user_id not in [russian.player1[0], russian.player2[0]]:
                rand_list = [
                    f"不要打扰 {russian.player1[1]} 和 {russian.player2[1]} 的决斗啊！",
                    f"给我好好做好一个观众！不然{BotConfig.self_nickname}就要生气了",
                    f"不要捣乱啊baka{uname}！",
                ]
                return (
                    MessageUtils.build_message(random.choice(rand_list)),
                    None,
                )

            # 修改点4：替换next_user为current_turn
            if user_id != russian.current_turn:
                current_player = (
                    russian.player1 if russian.current_turn == russian.player1[0]
                    else russian.player2
                )
                return (
                    MessageUtils.build_message(
                        f"现在不是你的回合！该 {current_player[1]} 开枪了!"
                    ),
                    None,
                )

            # 修改点5：重构子弹判定逻辑
            if russian.bullet_arr[russian.bullet_index] == 1:
                """中弹处理"""
                if shoot_type == "self":
                    # 打自己中弹，自己输
                    loser = russian.player1 if user_id == russian.player1[0] else russian.player2
                    winner = russian.player2 if user_id == russian.player1[0] else russian.player1
                    death_msg = random.choice([
                        '"嘭！"，你打中了自己！',
                        "天啊！你朝自己开枪了！",
                        "这一枪结结实实打在了自己身上..."
                    ])
                else:
                    # 打对方中弹，对方输
                    loser = russian.player2 if user_id == russian.player1[0] else russian.player1
                    winner = russian.player1 if user_id == russian.player1[0] else russian.player2
                    death_msg = random.choice([
                        '"嘭！"，你击中了对手！',
                        "子弹精准命中了目标！",
                        "这一枪结结实实打在了对手身上..."
                    ])

                russian.win_user = winner[0]  # 修改点6：记录赢家
                result = MessageUtils.build_message(
                    f"{death_msg} {loser[1]} 中弹了！"
                )
                settle = await self.settlement(group_id, loser[0], platform)
                return result, settle

            else:
                """空弹处理"""
                russian.bullet_index += 1
                remaining_bullets = sum(russian.bullet_arr[russian.bullet_index:])
                total_slots = len(russian.bullet_arr) - russian.bullet_index
                p = (remaining_bullets / total_slots * 100) if total_slots > 0 else 0

                if shoot_type == "self":
                    # 打自己空弹，回合不变
                    next_player = user_id
                    action_msg = random.choice([
                        "对着自己扣动扳机...咔！空弹！",
                        "惊险万分！对自己开枪但幸运地是空弹",
                        "你冒了一身冷汗，枪没响..."
                    ])
                else:
                    # 打对方空弹，交换回合
                    next_player = (
                        russian.player2[0] if user_id == russian.player1[0]
                        else russian.player1[0]
                    )
                    action_msg = random.choice([
                        "朝对手开枪...咔！空弹！",
                        "枪口对准对手但幸运地是空弹",
                        "你开了一枪，但什么也没发生..."
                    ])

                russian.current_turn = next_player  # 修改点7：更新当前回合
                next_player_name = (
                    russian.player1[1] if next_player == russian.player1[0]
                    else russian.player2[1]
                )

                self.__build_job(bot, group_id, True)
                return (
                    MessageUtils.build_message([
                        f"{action_msg}\n",
                        f"下一枪中弹概率: {p:.2f}%\n",
                        f"现在轮到 ",
                        At(flag="user", target=next_player),
                        f"({next_player_name}) 开枪！(开他/开我)"
                    ]),
                    None,
                )

        return (
            MessageUtils.build_message("目前没有进行的决斗，请发送 装弹 开启决斗吧！"),
            None,
        )

    async def settlement(
            self, group_id: str, user_id: str | None, platform: str | None = None
    ) -> UniMessage:
        """结算

        参数:
            group_id: 群组id
            user_id: 用户id
            platform: 平台

        返回:
            Text | MessageFactory: 返回消息
        """
        if not (russian := self._data.get(group_id)):
            return MessageUtils.build_message("比赛并没有开始...无法结算...")
        if not russian.player2:
            if self.__check_is_timeout(group_id):
                del self._data[group_id]
                return MessageUtils.build_message(
                    "规定时间内还未有人接受决斗，当前决斗过期..."
                )
            return MessageUtils.build_message("决斗还未开始,，无法结算哦...")
        if user_id and user_id not in [russian.player1[0], russian.player2[0]]:
            return MessageUtils.build_message("吃瓜群众不要捣乱！黄牌警告！")

        # 修改点1：优先使用预先设置的赢家(russian.win_user)
        if russian.win_user:
            # 如果已经有明确的赢家(比如在shoot方法中设置的)
            win_user = (
                russian.player1 if russian.win_user == russian.player1[0]
                else russian.player2
            )
            lose_user = (
                russian.player2 if russian.win_user == russian.player1[0]
                else russian.player1
            )
        else:
            # 修改点2：超时结算逻辑调整
            # 当前回合玩家就是输家(因为他没能在规定时间内开枪)
            lose_user = (
                russian.player1 if russian.current_turn == russian.player1[0]
                else russian.player2
            )
            win_user = (
                russian.player2 if russian.current_turn == russian.player1[0]
                else russian.player1
            )

        # 修改点3：移除无用的条件判断和current_turn设置
        if win_user and lose_user:
            rand = 0
            if russian.money > 10:
                rand = random.randint(0, 5)
                fee = int(russian.money * float(rand) / 100)
                fee = 1 if fee < 1 and rand != 0 else fee
            else:
                fee = 0

            winner = await RussianUser.add_count(win_user[0], group_id, "win")
            loser = await RussianUser.add_count(lose_user[0], group_id, "lose")
            await RussianUser.money(win_user[0], group_id, "win", russian.money - fee)
            await RussianUser.money(lose_user[0], group_id, "lose", russian.money)
            await UserConsole.add_gold(
                win_user[0], russian.money - fee, "russian", platform
            )
            try:
                await UserConsole.reduce_gold(
                    lose_user[0],
                    russian.money,
                    GoldHandle.PLUGIN,
                    "russian",
                    platform,
                )
            except InsufficientGold:
                if u := await UserConsole.get_user(lose_user[0]):
                    u.gold = 0
                    await u.save(update_fields=["gold"])

            result = [
                "这场决斗是 ",
                At(flag="user", target=win_user[0]),
                " 胜利了!",
            ]
            image = await text2image(
                f"结算：\n"
                f"\t胜者：{win_user[1]}\n"
                f"\t赢取金币：{russian.money - fee}\n"
                f"\t累计胜场：{winner.win_count}\n"
                f"\t累计赚取金币：{winner.make_money}\n"
                f"-------------------\n"
                f"\t败者：{lose_user[1]}\n"
                f"\t输掉金币：{russian.money}\n"
                f"\t累计败场：{loser.fail_count}\n"
                f"\t累计输掉金币：{loser.lose_money}\n"
                f"-------------------\n"
                f"哼哼，{BotConfig.self_nickname}从中收取了"
                f" {float(rand)}%({fee}金币) 作为手续费！\n"
                f"子弹排列：{russian.bullet_arr}",
                padding=10,
                color="#f9f6f2",
            )
            self.__remove_job(group_id)
            result.append(image)
            del self._data[group_id]
            return MessageUtils.build_message(result)

        return MessageUtils.build_message("赢家和输家获取错误...")

    async def __get_x_index(self, users: list[RussianUser], group_id: str):
        uid_list = [u.user_id for u in users]
        group_user_list = await GroupInfoUser.filter(
            user_id__in=uid_list, group_id=group_id
        ).all()
        group_user = {gu.user_id: gu.user_name for gu in group_user_list}
        data = []
        for uid in uid_list:
            if uid in group_user:
                data.append(group_user[uid])
            else:
                data.append(uid)
        return data

    async def rank(
        self, user_id: str, group_id: str, rank_type: str, num: int
    ) -> BuildImage | str:
        x_index = []
        data = []
        title = ""
        x_name = ""
        if rank_type == "a":
            users = (
                await RussianUser.filter(group_id=group_id, make_money__not=0)
                .order_by("make_money")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.make_money for u in users]
            title = "欧洲人排行"
            x_name = "金币"
        elif rank_type == "b":
            users = (
                await RussianUser.filter(group_id=group_id, lose_money__not=0)
                .order_by("lose_money")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.lose_money for u in users]
            title = "慈善家排行"
            x_name = "金币"
        elif rank_type == "lose":
            users = (
                await RussianUser.filter(group_id=group_id, fail_count__not=0)
                .order_by("fail_count")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.fail_count for u in users]
            title = "败场排行"
            x_name = "场次"
        elif rank_type == "max_lose":
            users = (
                await RussianUser.filter(group_id=group_id, max_losing_streak__not=0)
                .order_by("max_losing_streak")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.max_losing_streak for u in users]
            title = "最高连败排行"
            x_name = "场次"
        elif rank_type == "max_win":
            users = (
                await RussianUser.filter(group_id=group_id, max_winning_streak__not=0)
                .order_by("max_winning_streak")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.max_winning_streak for u in users]
            title = "最高连胜排行"
            x_name = "场次"
        elif rank_type == "win":
            users = (
                await RussianUser.filter(group_id=group_id, win_count__not=0)
                .order_by("win_count")
                .limit(num)
            )
            x_index = await self.__get_x_index(users, group_id)
            data = [u.win_count for u in users]
            title = "胜场排行"
            x_name = "场次"
        if not data:
            return "当前数据为空..."
        mat = BuildMat(MatType.BARH)
        mat.x_index = x_index
        mat.data = data  # type: ignore
        mat.title = title
        mat.x_name = x_name
        return await mat.build()


russian_manage = RussianManage()
