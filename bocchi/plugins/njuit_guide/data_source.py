import base64
from pathlib import Path
from typing import Optional
import httpx
from datetime import datetime
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from bocchi import ui
from playwright.async_api import async_playwright
from html import escape

from .config import njuit_config
from bocchi.configs.path_config import DATA_PATH, THEMES_PATH
from bocchi.services.log import logger

FILE_PATH = DATA_PATH / "njuit_guide"
TEMPLATES_PATH = THEMES_PATH / "default" / "templates" /"pages"/"extra"/ "njuit_guide"
save_path = FILE_PATH / "xiaoguo.png"
save_path.parent.mkdir(parents=True, exist_ok=True)
xg_path = TEMPLATES_PATH / "xg_template.html"
xg_path.parent.mkdir(parents=True, exist_ok=True)


class DataSource:
    @classmethod
    async def format_time(cls, full_time_str: str) -> str:
        """格式化时间字符串"""
        try:
            dt = datetime.strptime(full_time_str, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%m-%d %H:%M")
        except ValueError:
            return full_time_str

    @classmethod
    async def html_to_img(cls, html_content: str, output_path: Path = save_path) -> bool:
        """将HTML内容转换为图片"""
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": 375, "height": 812},
                    device_scale_factor=2,
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
                )
                page = await context.new_page()
                
                # 注入移动端meta标签
                if "<meta name=\"viewport\"" not in html_content:
                    html_content = html_content.replace(
                        "<head>", 
                        "<head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\">"
                    )
                
                await page.set_content(html_content, timeout=10_000, wait_until="networkidle")
                await page.screenshot(
                    path=str(output_path),
                    full_page=True,
                    type="jpeg",
                    quality=90,
                    timeout=15_000
                )
                return True
        except Exception as e:
            logger.error(f"截图失败:{e}")
            return False
        finally:
            if browser:
                await browser.close()

    @classmethod
    def _extract_data_from_response(cls, response_data, limit: int) -> list:
        """从API响应中提取数据列表"""
        if isinstance(response_data, list):
            return response_data[:limit]
        elif isinstance(response_data, dict):
            return response_data.get("rows", [])[:limit]
        return []

    @classmethod
    def _generate_images_html(cls, imgs: list, alt_text: str, class_name: str = "images") -> list:
        """生成图片HTML，支持自定义容器class用于样式匹配"""
        if not imgs:
            return []
        return [
            f'<div class="{class_name}">',
            *[f'<img src="{escape(img_url)}" alt="{alt_text}" loading="lazy">' for img_url in imgs],
            '</div>'
        ]

    @classmethod
    async def _get_comments(cls, client: httpx.AsyncClient, topic_id: str, cmt_num: int) -> list:
        """获取话题评论"""
        try:
            comments_url = f"{njuit_config.xg_comments_url}?topic_id={topic_id}&sort=hot&page=1"
            response = await client.get(comments_url)
            response.raise_for_status()
            comments_data = response.json().get("data", {})
            return cls._extract_data_from_response(comments_data, cmt_num)
        except Exception as e:
            logger.warning(f"获取话题 {topic_id} 的评论失败: {e}")
            return []

    @classmethod
    async def _generate_comment_html(cls, comment: dict) -> list:
        """生成评论HTML"""
        content = escape(comment.get("content", ""))
        time_str = await cls.format_time(comment.get("createTime", ""))
        nickname = escape(comment.get("userInfo", {}).get("nickname", "匿名用户"))
        
        html_parts = [
            '<div class="comment">',
            f'<div class="comment-header">',
            '<span class="icon">💬</span>',
            f'<span class="comment-author">{nickname}</span>',
            f'<span class="comment-time">{time_str}</span>',
            '</div>',
            f'<div class="comment-content">{content}</div>'
        ]
        
        # 处理评论图片
        html_parts.extend(cls._generate_images_html(comment.get("imgs", []), "评论图片", "comment-images"))
        
        # 处理回复
        html_parts.extend(await cls._generate_replies_html(comment.get("replys", {})))
        
        html_parts.append('</div>')
        return html_parts

    @classmethod
    async def _generate_replies_html(cls, replys_data) -> list:
        """生成回复HTML"""
        if not replys_data:
            return []
        
        replys = replys_data.get("rows", []) if isinstance(replys_data, dict) else replys_data
        if not replys:
            return []
        
        html_parts = ['<div class="replies-section">']
        for reply in replys:
            content = escape(reply.get("content", ""))
            time_str = await cls.format_time(reply.get("createTime", ""))
            nickname = escape(reply.get("userInfo", {}).get("nickname", "匿名用户"))
            
            html_parts.extend([
                '<div class="reply">',
                '<div class="reply-header">',
                '<span class="icon">↩️</span>',
                f'<span class="reply-author">{nickname}</span>',
                f'<span class="reply-time">{time_str}</span>',
                '</div>',
                f'<div class="reply-content">{content}</div>'
            ])
            
            # 处理回复图片
            html_parts.extend(cls._generate_images_html(reply.get("imgs", []), "回复图片", "reply-images"))
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        return html_parts

    @classmethod
    async def _generate_topic_html(cls, topic: dict, client: httpx.AsyncClient, cmt_num: int) -> list:
        """生成话题HTML"""
        content = escape(topic.get("content", ""))
        time_str = await cls.format_time(topic.get("createTime", ""))
        
        html_parts = [
            '<div class="topic">',
            f'<div class="topic-title">📌 {content}</div>',
            '<div class="topic-meta">',
            '<span class="icon">🕒</span>',
            f'<span>{time_str}</span>',
            '</div>'
        ]
        
        # 处理话题图片
        html_parts.extend(cls._generate_images_html(topic.get("imgs", []), "帖子图片", "topic-images"))
        
        # 处理评论
        comments = await cls._get_comments(client, topic["id"], cmt_num)
        if comments:
            html_parts.append('<div class="comments-section">')
            for comment in comments:
                html_parts.extend(await cls._generate_comment_html(comment))
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        return html_parts

    @classmethod
    async def get_topics(cls, tp_num: int, cmt_num: int, url: str) -> Optional[bytes]:
        """获取话题并生成图片（使用统一UI渲染）"""
        try:
            # 组装内容区域HTML
            content_parts: list[str] = []
            
            async with httpx.AsyncClient(headers=njuit_config.xg_headers, timeout=30.0) as client:
                response = await client.get(url)
                response_data = response.json().get("data", {})
                topics = cls._extract_data_from_response(response_data, tp_num)
                
                for topic in topics:
                    content_parts.extend(await cls._generate_topic_html(topic, client, cmt_num))

                content_html = "".join(content_parts)

                image_bytes = await ui.render_template(
                    "pages/extra/njuit_guide/xg_template.html",
                    data={"content": content_html},
                    viewport={"width": 386, "height": 10},
                )
                return image_bytes
                
        except Exception as e:
            logger.error(f"生成失败: {e}")
            return None
    
    @classmethod
    async def send_file(cls, file_path: Path, file_type: str) -> Message | str:
        """发送文件"""
        try:
            abs_path = file_path.absolute()
            if not abs_path.exists():
                available_files = "\n".join([f.name for f in FILE_PATH.glob("*")])
                logger.error(f"文件不存在，目录内容：\n{available_files}")
                return f"❌ {file_type}文件不存在（路径：{abs_path}）"
            
            if file_path.suffix == ".pdf":
                with open(abs_path, "rb") as f:
                    file_base64 = base64.b64encode(f.read()).decode()
                return Message(f"[CQ:file,file=base64://{file_base64},name={file_path.name}]")
            else:
                return Message(f"[CQ:image,file=file:///{abs_path}]")
        except Exception as e:
            logger.error(f"发送{file_type}失败: {e}")
            return f"❌ {file_type}发送失败：{str(e)}"
