from nonebot.plugin import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    #是否以wiki原图形式发送
    sgs_to_pic: bool = True
    #图片保存路径
    sgs_save_path: str = "data/sgs/"
    #最大公告数量
    sgs_max_news: int = 3

sgs_info_config:Config=get_plugin_config(Config)