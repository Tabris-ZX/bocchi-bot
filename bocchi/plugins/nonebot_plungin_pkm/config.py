from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    base_url: str = ""
    pkm_api_key: str = ""
    is_picture: bool = False



pkm_config: Config = get_plugin_config(Config)