import base64
import io
import time

from PIL import Image, ImageOps

from bocchi.services.log import logger
from bocchi.utils.http_utils import AsyncHttpx, get_client

from .config import drawer_config


async def build_img(img: bytes | None, prompt: str) -> bytes | int:
    return await _build_image(img, prompt, "drawer")


def _get_edit_image_upload_meta(img: bytes) -> tuple[str, str, str]:
    try:
        with Image.open(io.BytesIO(img)) as image:
            if (image.format or "").upper() == "JPEG":
                return "JPEG", "image.jpg", "image/jpeg"
    except Exception:
        pass
    return "PNG", "image.png", "image/png"


def prepare_edit_image(img: bytes, max_size: int = 1280) -> tuple[bytes, str, str]:
    image_format, filename, mime_type = _get_edit_image_upload_meta(img)
    try:
        with Image.open(io.BytesIO(img)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((max_size, max_size))

            if image_format == "JPEG":
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
            elif image.mode not in {"RGBA", "LA", "L"}:
                image = image.convert("RGBA")

            output = io.BytesIO()
            save_kwargs = {"format": image_format, "optimize": True}
            if image_format == "JPEG":
                save_kwargs["quality"] = 95
            image.save(output, **save_kwargs)
            return output.getvalue(), filename, mime_type
    except Exception as e:
        logger.warning(f"编辑图片预处理失败，使用原图: {e}", "drawer", e=e)
        return img, filename, mime_type


async def _decode_image(payload: dict, log_name: str) -> bytes | None:
    data_list = payload.get("data") or []
    if not data_list:
        logger.error("Images/edits 响应无 data 字段", log_name)
        return None

    image_data = data_list[0]
    b64_data = image_data.get("b64_json")
    if b64_data:
        try:
            return base64.b64decode(b64_data)
        except Exception as e:
            logger.error(f"b64 解码失败: {e}", log_name, e=e)
            return None

    image_url = image_data.get("url")
    if image_url:
        try:
            return await AsyncHttpx.get_content(image_url, timeout=120.0)
        except Exception as e:
            logger.error(f"下载返回图片失败: {e}", log_name, e=e)
            return None

    logger.error("图像接口响应缺少 b64_json 和 url", log_name)
    return None


async def _build_image(
    img: bytes | None,
    prompt: str,
    log_name: str,
    quality: str = "standard",
) -> bytes | int:
        
    key = drawer_config.get_api_key()
    if not key:
        logger.error("未配置 DRAWER_KEY，无法调用绘图接口", log_name)
        return 503

    headers = {"Authorization": f"Bearer {key}"}
    payload = {
        "prompt": prompt,
        "model": drawer_config.model,
        "size": "1024x1024",
    }
    if quality:
        payload["quality"] = quality
    if img is None:
        payload["response_format"] = "b64_json"
    if img is not None:
        endpoint = "images/edits"
    else:
        endpoint = "images/generations"

    url = f"{drawer_config.base_url}/{endpoint}"
    try:
        start_time = time.perf_counter()
        if img is not None:
            prepared_img, filename, mime_type = prepare_edit_image(img)
            response = await get_client().post(
                url,
                headers=headers,
                data=payload,
                files={"image": (filename, prepared_img, mime_type)},
                timeout=360.0,
            )
        else:
            response = await get_client().post(
                url,
                headers=headers,
                json=payload,
                timeout=360.0,
            )

        elapsed = time.perf_counter() - start_time
        if response.status_code == 200:
            try:
                payload = response.json()
            except Exception as e:
                logger.error(f"drawer {endpoint} 响应 JSON 解析失败: {e}", log_name, e=e)
                return response.status_code
            image = await _decode_image(payload, log_name)
            if not image:
                return response.status_code
                
            return image
        else:
            logger.error(
                f"drawer {endpoint} 请求失败: status={response.status_code}, elapsed={elapsed:.2f}s, body={response.text[:1000]}",
                log_name,
            )
            return response.status_code
    except Exception as e:
        logger.error(f"drawer {endpoint} 请求异常: {e}", log_name, e=e)
        return 500
