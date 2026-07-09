from pathlib import Path

import asyncio
import json
from nonebot_plugin_uninfo import Uninfo

from bocchi.utils.message import MessageUtils
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args, Arparma, At, Image, Reply, UniMessage, on_alconna, Option
)
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from bocchi.configs.utils import PluginExtraData, RegisterConfig
from bocchi.models.user_console import UserConsole
from bocchi.utils.enum import GoldHandle
from bocchi.utils.http_utils import AsyncHttpx
from bocchi.utils.platform import PlatformUtils

from .config import drawer_config
from .data_source import build_img
from .queue_manager import DrawerRequestQueue

PROMPTS_FILE = Path(__file__).with_name("prompts.json")
SENSITIVE_WORDS_FILE = Path(__file__).with_name("sensitive_words.json")
drawer_request_queue = DrawerRequestQueue(drawer_config.request_interval_seconds)


__plugin_meta__ = PluginMetadata(
    name="ai作图",
    description="使用 gpt-image2 制作各种图片,可是有代价的!",
    usage="""
    普通指令:
        图片创作 -p <提示词> [图片]
        图片创作 -t <模板名> ?-p <额外要求> <图片>
        图片创作 -l (查看当前可用的 prompt 模板)
        (前缀 "drawer" 同样有效)
    todo:
        - [ ] 支持上传模板
        - [ ] 支持自定义画质/尺寸
    示例:
        图片创作 -p 画一只海豚
        drawer -p 给这张图片改为黑白色调 @某人
        drawer -t 至上主义 [图片]
    """.strip(),
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="1.0.3",
        configs=[
            RegisterConfig(
                key="DRAWER_KEY",
                value=None,
                help="Drawer接口密钥",
            ),
            RegisterConfig(
                key="DRAWER_BASE_URL",
                value="https://api.openai.com/v1",
                help="OpenAI兼容API基础地址，如 `https://api.openai.com/v1` 或代理"
            ),
            RegisterConfig(
                key="DRAWER_MODEL",
                value="gpt-image-2",
                help="OpenAI兼容图像模型名称"
            ),
            RegisterConfig(
                key="BASE_COST",
                value="100",
                help="基础金币消耗量"
            ),
            RegisterConfig(
                key="DRAWER_REQUEST_INTERVAL",
                value="60",
                help="作图请求队列间隔秒数，默认 60 秒"
            ),
        ],
    ).to_dict(),
)

draw = on_alconna(
    Alconna(
        "图片创作",
        Option("-t", Args["name", str]),
        Option("-p", Args["prompt", str]),
        Args["image?", Image | At],
    ),
    aliases={"drawer", "ai作画"},
    priority=5,
    block=True,
)

ls = on_alconna(
    Alconna(
        "图片创作 -l",
    ),
    aliases={"drawer"},
    priority=5,
    block=True,
)

# def get_sensitive_words() -> list[str]:
#     if not SENSITIVE_WORDS_FILE.exists():
#         return []

#     try:
#         data = json.loads(SENSITIVE_WORDS_FILE.read_text(encoding="utf-8"))
#     except Exception:
#         return []

#     words = data.get("words", [])
#     if not isinstance(words, list):
#         return []
#     return [str(word).strip() for word in words if str(word).strip()]



# def find_sensitive_word(text: str) -> str | None:
#     normalized_text = text.casefold()
#     for word in get_sensitive_words():
#         normalized_word = word.casefold()
#         if normalized_word and normalized_word in normalized_text:
#             return word
#     return None


@draw.handle()
async def handle_draw(bot, event, params: Arparma, session: Uninfo):
    cst = 91
    user = await UserConsole.get_user(str(session.user.id))
    if user.gold < cst:
        await MessageUtils.build_message("你的金币不足了~攒点钱再来吧~").finish()
    image = params.query("image") or await reply_fetch(event, bot)
    if isinstance(image, Reply) and not isinstance(image.msg, str):
        image = await UniMessage.generate(message=image.msg, event=event, bot=bot)
        for i in image:
            if isinstance(i, Image):
                image = i
                break

    template_name = params.query("name")
    custom_prompt = params.query("prompt")
    prompt = bulid_prompt(template_name, custom_prompt) or ""

    if template_name and not prompt:
        await UniMessage(
            f"没有找到名为 `{template_name}` 的模板哦~\n{list_templates()}"
        ).finish(reply_to=True)
    if not prompt:
        await UniMessage("请使用 `-p <提示词>`、`-t <模板名>` 哦~").finish(reply_to=True)
    if template_name and not isinstance(image, Image | At):
        await UniMessage("使用模板作图时必须提供图片哦~").finish(reply_to=True)

    # sensitive_word = find_sensitive_word(prompt)
    # if sensitive_word:
    #     await UniMessage(
    #         f"提示词中包含敏感内容，禁止作图哦~\n命中词：{sensitive_word}"
    #     ).finish(reply_to=True)

    queue_token, queue_position, eta_seconds = await drawer_request_queue.enter()
    if queue_position > 0:
        await UniMessage(
            f"当前作图请求较多，已加入等待队列~\n前方还有 {queue_position} 个请求，预计等待约 {eta_seconds} 秒。"
        ).send(reply_to=True)
    else:
        await UniMessage("正在处理中~").send(reply_to=True)
    try:
        await drawer_request_queue.wait_turn(queue_token)
        if isinstance(image, Image) and image.url:
            image_bytes = await AsyncHttpx.get_content(image.url)
        elif isinstance(image, At):
            image_bytes = await PlatformUtils.get_user_avatar(image.target, "qq")
        else:
            image_bytes = None
        if not image_bytes:
            image_bytes = None
        if template_name and not image_bytes:
            await UniMessage("使用模板作图时必须提供图片哦~").finish(reply_to=True)
        msg = await build_img(image_bytes, prompt)
    except Exception:
        await drawer_request_queue.cancel(queue_token)
        raise
    finally:
        if queue_token.done() and not queue_token.cancelled():
            asyncio.create_task(drawer_request_queue.leave())

    if isinstance(msg, bytes):
        await UserConsole.reduce_gold(user.user_id, cst, GoldHandle.PLUGIN, "drawer")
        await MessageUtils.build_message(msg).send()
    elif msg == 429:
        await MessageUtils.build_message("太快了吧~ 请5分钟后再试吧~").finish(reply_to=True)
    else:
        await MessageUtils.build_message(f"状态码{msg},图片生成失败,肯定不是波奇的问题!").finish(reply_to=True)

@ls.handle()
async def handle_ls(bot, event, params: Arparma, _session: Uninfo):
    await UniMessage(list_templates()).finish(reply_to=True)

def get_prompt_templates():
    data = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
    prompts = {item["name"]: item["prompt"] for item in data["prompts"]}
    return prompts

def get_prompt_template(name: str) -> str | None:
    return get_prompt_templates().get(name)


def bulid_prompt(template_name: str | None, custom_prompt: str | None) -> str | None:
    template_prompt = get_prompt_template(template_name) if template_name else None
    custom_prompt = custom_prompt.strip() if isinstance(custom_prompt, str) and custom_prompt.strip() else None

    if template_name and not template_prompt:
        return None
    if template_prompt and custom_prompt:
        return f"{template_prompt}\n\n额外要求：{custom_prompt}"
    return template_prompt or custom_prompt

def list_templates() -> str:
    templates = get_prompt_templates()
    if not templates:
        return "当前还没有可用的 prompt 模板哦~"
    names = [f"{index}. {name}" for index, name in enumerate(sorted(templates.keys()), start=1)]
    return "可用模板：\n" + "\n".join(names)