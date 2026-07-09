
from playwright.async_api import FloatRect, async_playwright
from nonebot.log import logger
from .config import sgs_info_config
from pathlib import Path

save_path = sgs_info_config.sgs_save_path
roles_save_path = save_path + "roles/"

news_save_path = save_path + "news/"

class Util:
     
    @classmethod
    async def page_to_img(cls, url: str, name: str,is_news: bool = False) -> bool:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                if is_news:
                    Path(news_save_path).mkdir(parents=True, exist_ok=True)
                    context = await browser.new_context(
                    viewport={'width': 390, 'height': 844},  # iPhone 12的屏幕分辨率
                    device_scale_factor=3,  # iPhone 12的设备像素比
                    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
                    )
                    page = await context.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(1000)
                    await page.screenshot(
                            path=news_save_path + f"{name}.png",
                            full_page=True,
                            type='png',
                            timeout=30000
                        )
                    return True
                else:
                    context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    device_scale_factor=2,
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    )
                    page = await context.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)
                    # 直接隐藏所有可能遮挡的元素
                    await page.evaluate("""() => {
                        // 隐藏整个导航栏
                        const navBar = document.querySelector('.wiki-nav');
                        if (navBar) {
                            navBar.style.display = 'none';
                            navBar.style.visibility = 'hidden';
                            navBar.style.height = '0';
                            navBar.style.overflow = 'hidden';
                        }
                    }""")

                    await page.wait_for_timeout(500)

                    start_element = await page.query_selector(".mw-parser-output")
                    if not start_element:
                        logger.error("Start element not found!")
                        return False

                    Path(roles_save_path).mkdir(parents=True, exist_ok=True)
                    await start_element.screenshot(
                        path=roles_save_path + f"{name}.png",
                        type='png',
                        timeout=10000
                    )
                    
                    logger.info("Screenshot with hidden fixed elements")
                    return True
            
            except TimeoutError as e:
                logger.error(f"TimeoutError: {e}")
                return False
            except Exception as e:
                logger.error(f"Error: {e}")
                return False
            finally:
                await browser.close()

    @classmethod
    async def clean_img(cls):
        for dir_path in [Path(roles_save_path), Path(news_save_path)]:
            if not dir_path.exists():
                continue
            for file in dir_path.iterdir():
                if file.is_file():
                    file.unlink()