import os
from pathlib import Path
import platform

import aiofiles
import nonebot
from nonebot import on_command
from nonebot.adapters import Bot
from nonebot.params import ArgStr
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_uninfo import Uninfo

from bocchi.configs.config import BotConfig
from bocchi.configs.utils import PluginExtraData
from bocchi.services.log import logger
from bocchi.utils.enum import PluginType
from bocchi.utils.message import MessageUtils
from bocchi.utils.platform import PlatformUtils

__plugin_meta__ = PluginMetadata(
    name="重启/关机",
    description="执行脚本重启/关机波奇",
    usage="""
    重启/关机
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier", version="0.1", plugin_type=PluginType.SUPERUSER
    ).to_dict(),
)

driver = nonebot.get_driver()

RESTART_MARK = Path() / "is_restart"
SHUTDOWN_MARK = Path() / "is_shutdown"  # !!! Added: 关机标记文件
RESTART_FILE = Path("tools") / "restart.sh"

_matcher = on_command(
    "重启",
    permission=SUPERUSER,
    rule=to_me(),
    priority=1,
    block=True,
)
power_off_matcher = on_command(
    "关机",
    permission=SUPERUSER,
    rule=to_me(),
    priority=1,
    block=True,
)

@_matcher.got(
    "flag",
    prompt=f"确定是否重启{BotConfig.self_nickname}？\n确定请回复[是|好|确定]\n（重启失败咱们将失去联系，请谨慎！）",
)
async def _(bot: Bot, session: Uninfo, flag: str = ArgStr("flag")):
    if flag.lower() in {"true", "是", "好", "确定", "确定是"}:
        await MessageUtils.build_message(
            f"开始重启{BotConfig.self_nickname}..请稍等..."
        ).send()
        async with aiofiles.open(RESTART_MARK, "w", encoding="utf8") as f:
            await f.write(f"{bot.self_id} {session.user.id}")
        logger.info("开始重启波奇...", "重启", session=session)
        if str(platform.system()).lower() == "windows":
            import sys
            python = sys.executable
            os.execl(python, python, *sys.argv)
        else:
            if not os.access("./tools/restart.sh", os.X_OK):  # !!! Modified: 检查执行权限
                os.system("chmod +x ./tools/restart.sh")      # !!! Modified: 自动赋权
            os.system("./tools/restart.sh")  # noqa: ASYNC221
    else:
        await MessageUtils.build_message("已取消操作...").send()


@driver.on_bot_connect
async def _(bot: Bot):
    if str(platform.system()).lower() != "windows" and not RESTART_FILE.exists():
        async with aiofiles.open(RESTART_FILE, "w", encoding="utf8") as f:
            await f.write(
                "#!/bin/bash\n"
                "# 终止所有 bocchi 相关进程（launcher + worker）\n"
                "pkill -f 'bocchi.cli' 2>/dev/null\n"
                "sleep 1\n\n"
                "# 确保端口已释放\n"
                "for i in $(seq 1 10); do\n"
                "    if ! ss -tlnp | grep -q ':"
                + str(bot.config.port)
                + "[[:space:]]'; then\n"
                "        break\n"
                "    fi\n"
                "    pid=$(ss -tlnp | grep ':"
                + str(bot.config.port)
                + "[[:space:]]' | grep -oP 'pid=\\K[0-9]+' | head -1)\n"
                "    [ -n \"$pid\" ] && kill -9 \"$pid\" 2>/dev/null\n"
                "    sleep 1\n"
                "done\n\n"
                "cd /home/zx/work/bot && uv run zx\n"
            )
        os.system("chmod +x ./tools/restart.sh")  # noqa: ASYNC221
        logger.info("已自动生成 restart.sh(重启) 文件，请检查脚本是否与本地指令符合...")
    if RESTART_MARK.exists():
        async with aiofiles.open(RESTART_MARK, encoding="utf8") as f:
            bot_id, user_id = (await f.read()).split()
        if bot := nonebot.get_bot(bot_id):
            if target := PlatformUtils.get_target(user_id=user_id):
                await MessageUtils.build_message(
                    f"{BotConfig.self_nickname}已成功重启！"
                ).send(target, bot=bot)
        RESTART_MARK.unlink()

    # !!! Added: 启动时检查关机标记
    if SHUTDOWN_MARK.exists():
        async with aiofiles.open(SHUTDOWN_MARK, encoding="utf8") as f:
            bot_id, user_id = (await f.read()).split()
        if bot := nonebot.get_bot(bot_id):
            if target := PlatformUtils.get_target(user_id=user_id):
                await MessageUtils.build_message(
                    f"{BotConfig.self_nickname} 上次被主动关闭，现已重新启动。"
                ).send(target, bot=bot)
        SHUTDOWN_MARK.unlink()


@power_off_matcher.got(
    "flag",
    prompt=f"确定是否关闭{BotConfig.self_nickname}？\n确定请回复[是|好|确定]\n（关机后需手动重新启动！）",
)
async def _(bot: Bot, session: Uninfo, flag: str = ArgStr("flag")):
    if flag.lower() in {"1", "是", "好", "确定"}:  # !!! Modified: 支持更多确认词
        await MessageUtils.build_message(
            f"开始关闭{BotConfig.self_nickname}... 再见！"
        ).send()
        logger.info(f"用户 {session.user.id} 触发关机", "关机", session=session)
        
        # !!! Added: 记录关机操作者
        async with aiofiles.open(SHUTDOWN_MARK, "w", encoding="utf8") as f:
            await f.write(f"{bot.self_id} {session.user.id}")

        if str(platform.system()).lower() == "windows":
            import signal
            os.kill(os.getpid(), signal.SIGTERM)  # !!! Modified: 优雅退出
        else:
            os.system("pkill -f 'bocchi.cli'")  # !!! Modified: 匹配 launcher + worker
    else:
        await MessageUtils.build_message("已取消关机操作").send()