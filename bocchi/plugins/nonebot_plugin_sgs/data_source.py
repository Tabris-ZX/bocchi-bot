from nonebot.log import logger

from bs4 import BeautifulSoup
import requests
from .config import sgs_info_config
from .util import Util
from pathlib import Path

wiki_base_url = "https://wiki.biligame.com/sgs/"
news_url = "https://x.sanguosha.com/"
save_path = sgs_info_config.sgs_save_path
roles_save_path = save_path + "roles/"
news_save_path = save_path + "news/"

class DataSource:

    @classmethod
    async def get_roles_info(cls, name:str):
        url=wiki_base_url+f"{name}"
        
        if sgs_info_config.sgs_to_pic: # 保存为图片
            if not Path(save_path).exists():
                Path(save_path).mkdir(parents=True, exist_ok=True)
            if not Path(roles_save_path+f"{name}.png").exists():
                if not await Util.page_to_img(url, name):
                    logger.error(f"截图失败: {name}")
                    return "截图失败"
            return Path(roles_save_path+f"{name}.png")

        else: # 保存为文本
            response = requests.get(url)
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            # ====== 硬编码抓技能台词 ======
            result = []
            # 找到所有版本标题（经典版本 / 界限突破版本 / 国战版本）
            for h2 in soup.find_all("h2"):
                version_name = h2.get_text(strip=True)
                if version_name=="目录":
                    continue
                else:
                    version = {"version_name": version_name, "skills": [], "lines": []}

                    # 技能部分
                    if version_name=="自走棋":
                        container = h2.find_next("div", class_="themed-container flex-container col-direction")
                        if not container:
                            continue
                        skills_container = container.find("div", class_="character-lines-and-skills-section equal-divide") #type: ignore

                        line_title = None
                    else:
                        container = h2.find_next("div", class_="character-lines-and-skills-section")
                        if not container:
                            continue
                        skill_title = container.find("div", string="技能") #type: ignore
                        skills_container = skill_title.find_next_sibling("div", class_="flex-container col-direction")#type: ignore

                        line_title = container.find("div", string="台词") #type: ignore
                    if skills_container:
                        for flex_div in skills_container.find_all("div", class_="flex-container", recursive=False): #type: ignore
                            name_div = flex_div.find("div", class_="basic-info-row-label") #type: ignore
                            desc_div = name_div.find_next_sibling("div") if name_div else None
                            if name_div and desc_div:
                                skill_name = name_div.get_text(strip=True)
                                skill_desc = desc_div.get_text(strip=True)
                                version["skills"].append({
                                    "name": skill_name,
                                    "desc": skill_desc
                                })
                    # 台词部分
                    if line_title:
                        lines_container = line_title.find_next_sibling("div")
                        for flex_div in lines_container.find_all("div", class_="flex-container", recursive=False): #type: ignore
                            name_div = flex_div.find("div", class_="basic-info-row-label") #type: ignore
                            content_div = name_div.find_next_sibling("div") if name_div else None
                            if name_div and content_div:
                                version["lines"].append({
                                    "skill": name_div.get_text(strip=True),
                                    "text": content_div.get_text(strip=True)
                                })
                    result.append(version)
            for v in result[1:]:
                print(v["version_name"])
                print("技能：")
                for s in v["skills"]:
                    print(f"  {s['name']}：{s['desc']}")
                print("台词：")
                for l in v["lines"]:
                    print(f"  {l['skill']}：{l['text']}")
                print()

            # ====== 硬编码抓皮肤 ======
            # 找到皮肤表格
            table = soup.find("table", class_="styled-wikitable")

            if not table:
                logger.info("没找到皮肤表格，可能是页面结构不同或反爬", "sgs")
            else:
                rows = table.find_all("tr")[1:]  # 跳过表头 #type: ignore
                for row in rows:
                    cols = row.find_all("td") #type: ignore
                    if not cols:
                        continue
                    skin_name = cols[0].get_text(strip=True)
                    painter = cols[1].get_text(strip=True)
                    static_get = cols[2].get_text(strip=True)
                    dynamic_get = cols[3].get_text(strip=True)
                    release_date = cols[4].get_text(strip=True)

                    print(
                        f"皮肤名:{skin_name} 画师:{painter} 静态获取: {static_get} 动态获取:{dynamic_get} 上线时间:{release_date}")

    @classmethod
    async def get_news_info(cls)->list[str]:
        # 模拟请求，获取页面HTML
        response = requests.get(news_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        # 存储新闻链接和日期
        news_list = []

        li_tags = soup.find_all('li', class_='show')
        for li_tag in li_tags:
            a_tags = li_tag.find_all('a') #type: ignore
            for a_tag in a_tags:
                href = a_tag.get('href') #type: ignore
                if  href is None or not href.startswith("/news/2025"): #type: ignore
                    continue
                news_date = a_tag.find('span', class_='news-date').text.strip() #type: ignore
                try:
                    
                    if len(news_list)<sgs_info_config.sgs_max_news:
                        news_list.append(href)
                except ValueError as e:
                    logger.info(f"错误的日期格式: {news_date}, 跳过该项", "sgs")
                    continue
        return news_list
    
    @classmethod
    async def build_news_img(cls)->list[Path]:
        def _sanitize_news_name(raw: str) -> str:
            # 去掉开头的斜杠，并将路径分隔符替换为下划线，避免深层目录
            cleaned = raw.lstrip("/")
            return cleaned.replace("/", "_")

        Path(news_save_path).mkdir(parents=True, exist_ok=True)
        news_img_path: list[Path] = []
        news_list = await cls.get_news_info()
        for news in news_list:
            file_name = _sanitize_news_name(news)
            file_path = Path(news_save_path + f"{file_name}.png")
            if file_path.exists():
                news_img_path.append(file_path)
                continue
            if await Util.page_to_img(news_url + news, file_name, is_news=True):
                news_img_path.append(file_path)
        return news_img_path