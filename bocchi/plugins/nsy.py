from random import choice, sample
from pathlib import Path
from datetime import datetime

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Image, Arparma, Reply, UniMessage
from nonebot_plugin_alconna.uniseg.tools import reply_fetch

from bocchi.configs.path_config import DATA_PATH
from bocchi.configs.utils import Command, PluginExtraData
from bocchi.services.log import logger
from bocchi.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="nsy图片发送",
    description="怎么这么多nsyc啊~\n为什么什么照片都往上放啊喂,脱离本意了啊!~",
    usage="""
    nsy ?[名字] ?[num=1]: 发送指定名字的图片(为空则全局随机)，num为数量
    上传 [名字] [图片]: 上传图片到指定名字的目录；也可先引用一张图片后发送：上传 [名字]
    """,
    extra=PluginExtraData(
        author="Tabris-ZX",
        version="0.4",
        commands=[
            Command(command="nsy <名字>", description="发送指定名字的图片(为空则随机发送)"),
            Command(command="上传 <名字> <图片>", description="上传图片到指定名字的目录")
        ],
    ).to_dict(),
)

nsy_path: Path = DATA_PATH / "nsy"

_matcher = on_alconna(
    Alconna(
        "nsy",
        Args["name?", str, ""],
        Args["num?", int, 1],
    ),
    priority=5,
    block=True,
)

upload_matcher = on_alconna(
    Alconna(
        "上传",
        Args["name", str],
        Args["image?", Image],
    ),
    priority=5,
    block=True,
)

# 挑选目录下图片
valid_exts = {".png"}
def pick_images_from_dir(directory: Path, count: int) -> list[Path]:
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in valid_exts]
    if not files:
        return []
    return sample(files, min(count, len(files)))

@_matcher.handle()
async def send_nsy(name: str, num: int):
    num = max(num, 1)
    if not nsy_path.exists() or not nsy_path.is_dir():
        await MessageUtils.build_message("图片目录不存在: data/nsy").finish()

    # 获取图片列表
    img_paths: list[Path] = []
    if not name or name == "随机":
        # 全局随机：遍历所有子目录聚合后抽取
        all_images: list[Path] = []
        for sub in nsy_path.iterdir():
            if sub.is_dir():
                all_images.extend(p for p in sub.iterdir() if p.is_file() and p.suffix.lower() in valid_exts)
        if not all_images:
            await MessageUtils.build_message("目录中没有可用的图片: data/nsy/*").finish()
        img_paths = sample(all_images, min(num, len(all_images)))
    else:
        # 按名字包含匹配目录：当输入包含某个目录名时匹配；多个则按字典序取最前
        try:
            sub_names = [d.name for d in nsy_path.iterdir() if d.is_dir()]
        except FileNotFoundError:
            sub_names = []
        name_lower = name.lower()
        candidates = [n for n in sub_names if name_lower in n.lower()]
        if not candidates:
            await MessageUtils.build_message(f"目录中没有匹配的图片集: {name}").finish()
        name = sorted(candidates)[0]
        base_dir = nsy_path / name
        img_paths = pick_images_from_dir(base_dir, num)
        if not img_paths:
            await MessageUtils.build_message(f"目录中没有可用的图片: data/nsy/{name}").finish()

    # 发送图片
    if len(img_paths) == 1:
        await MessageUtils.build_message(img_paths[0]).send()
    else:
        alc_msg= MessageUtils.build_message(img_paths) #type: ignore
        await MessageUtils.alc_forward_msg(alc_msg, '3541219424', '可爱的小波奇').send()

    log_name = name or "随机"
    logger.info(f"发送 nsy {log_name} 图片: {len(img_paths)} 张")

@upload_matcher.handle()
async def upload(bot, event, params: Arparma):
    """上传图片到指定目录，支持直接带图或引用图片后发送命令"""
    try:
        name = params.query("name")
        if not name:
            await MessageUtils.build_message("请提供目录名：上传 [名字] [图片]").finish(reply_to=True)

        # 确保根目录存在
        nsy_path.mkdir(parents=True, exist_ok=True)
        
        # 创建或获取目标子目录
        target_dir = nsy_path / name
        target_dir.mkdir(exist_ok=True)
        
        # 生成唯一文件名（时间戳 + 随机数）
        timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
        # import random
        # random_suffix = random.randint(1000, 9999)

        # 获取图片：优先参数 image，其次尝试从引用消息中提取
        image = params.query("image") or await reply_fetch(event, bot)
        if isinstance(image, Reply) and not isinstance(image.msg, str):
            # 展开引用内容并从中提取第一张图片
            uni = await UniMessage.generate(message=image.msg, event=event, bot=bot)
            for seg in uni:
                if isinstance(seg, Image):
                    image = seg
                    break
        
        source_bytes: bytes | None = None
        source_path: str | None = None
        source_url: str | None = None

        if isinstance(image, Image):
            if image.raw:
                if isinstance(image.raw, bytes):
                    source_bytes = image.raw
                elif hasattr(image.raw, "getvalue"):
                    source_bytes = image.raw.getvalue()
            if not source_bytes and getattr(image, "path", None):
                source_path = image.path  # type: ignore
            if not source_bytes and not source_path and getattr(image, "url", None):
                source_url = image.url  # type: ignore
        
        if not (source_bytes or source_path or source_url):
            await MessageUtils.build_message("未检测到图片，请直接带图发送，或引用一张图片再发送本命令").finish(reply_to=True)
            return

        # 仅保存为 png
        ext = ".png"
        filename = f"{timestamp}{ext}"
        file_path = target_dir / filename

        # 写入文件
        if source_bytes is not None:
            with open(file_path, "wb") as f:
                f.write(source_bytes)
        elif source_path:
            import shutil
            shutil.copy2(source_path, file_path)
        elif source_url:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(source_url)
                with open(file_path, "wb") as f:
                    f.write(resp.content)

        # 验证文件是否成功保存
        if file_path.exists() and file_path.stat().st_size > 0:
            await MessageUtils.build_message(f"图片上传成功！").send(reply_to=True)
            logger.info(f"图片上传成功: {file_path}", "上传")
        else:
            await MessageUtils.build_message("图片上传失败，请重试").finish(reply_to=True)
    
    except Exception as e:
        logger.error(f"图片上传失败: {e}", "上传", e=e)
        await MessageUtils.build_message(f"图片上传失败: {str(e)}").finish(reply_to=True)
    

