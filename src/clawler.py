from selenium import webdriver
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests as req_lib
import random
import time
import re
import os


# 处理爬取到的HTML文本
def process_text(html_content):
    # 移除"內容加載失敗"等提示文本
    html_content = re.sub(r"[（(]內容加載失敗[^)）]*[)）]", "", html_content)
    processed = re.sub(r"(?i)</\s*p\s*>", "\n", html_content)
    processed = re.sub(r"<[^>]+>", "", processed)
    processed = re.sub(r"\n+", "\n", processed).strip()
    return processed


# 用requests直接获取章节内容作为回退方案
def fetch_content_via_requests(chapter_url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
            "Referer": "https://www.linovelib.com/",
        }
        resp = req_lib.get(chapter_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            match = re.search(
                r'id="TextContent"[^>]*>(.*?)</div>', resp.text, re.DOTALL
            )
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


# 处理文件名中的特殊字符
def sanitize_filename(filename):
    # 替换Windows文件系统不允许的字符
    invalid_chars = r'[\\/:*?"<>|]'
    # 替换为下划线
    sanitized = re.sub(invalid_chars, "_", filename)
    # 移除前后的空白字符
    sanitized = sanitized.strip()
    return sanitized


# 输入小说的目录页网址
URL = input("请输入小说的目录页网址(多个网址请用空格分隔):")
urls = [url.strip() for url in URL.split()]

# 驱动配置
options = Options()
# 反自动化检测
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
)
# CI环境下使用headless模式
if os.environ.get("CI"):
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
driver = webdriver.Edge(options=options)
# 移除 navigator.webdriver 标记
driver.execute_cdp_cmd(
    "Page.addScriptToEvaluateOnNewDocument",
    {"source": 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'},
)
wait = WebDriverWait(driver, 30)


for url in urls:
    driver.get(url)
    time.sleep(3)
    print(f"Page URL: {driver.current_url}")
    print(f"Page title: {driver.title}")

    # 爬取书名 - 使用CSS选择器，更灵活
    try:
        book_title_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".book-title, h1"))
        )
        book_title = book_title_el.text.strip()
    except TimeoutException:
        print("无法获取书名，跳过此URL")
        print(f"Page source (first 2000 chars): {driver.page_source[:2000]}")
        continue

    safe_title = sanitize_filename(book_title)
    print(f"书名: {book_title}")

    # 从目录页提取所有章节链接
    chapter_links = []
    # 提取小说ID用于匹配章节链接
    novel_id_match = re.search(r"/novel/(\d+)", url)
    if not novel_id_match:
        print("无法从URL中提取小说ID，跳过")
        continue
    novel_id = novel_id_match.group(1)

    all_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
    for link in all_links:
        href = link.get_attribute("href") or ""
        # 匹配章节链接: /novel/{id}/{chapter_id}.html (排除 vol_ 卷页和 catalog)
        if re.search(rf"/novel/{novel_id}/\d+\.html$", href):
            title = link.text.strip()
            if title and href not in [c[1] for c in chapter_links]:
                chapter_links.append((title, href))

    print(f"共找到 {len(chapter_links)} 个章节")

    if not chapter_links:
        print("未找到任何章节链接，跳过")
        continue

    # 爬取每个章节
    with open("novel/" + safe_title + ".txt", "w+", encoding="utf-8") as f:
        for i, (ch_title, ch_url) in enumerate(chapter_links):
            try:
                print(f"[{i+1}/{len(chapter_links)}] {ch_title}")
                driver.get(ch_url)
                time.sleep(random.randint(1, 3))

                # 爬取章节标题
                try:
                    part_title = wait.until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                "#mlfy_main_text h1, .read-title, .chapter-title, h1",
                            )
                        )
                    ).text
                except TimeoutException:
                    part_title = ch_title
                f.write("\n" + part_title + "\n\n")

                # 爬取章节内容
                content_html = None
                try:
                    # 等待内容元素出现且包含文本（JS渲染完成）
                    def content_loaded(drv):
                        try:
                            el = drv.find_element(By.ID, "TextContent")
                            text = el.text.strip()
                            # 内容足够长且不含加载失败提示
                            if len(text) > 10 and "內容加載失敗" not in text:
                                return el
                            return False
                        except Exception:
                            return False

                    article_el = WebDriverWait(driver, 15).until(content_loaded)
                    content_html = article_el.get_attribute("innerHTML")
                except (TimeoutException, Exception):
                    pass

                # 回退：直接用requests获取
                if not content_html or "內容加載失敗" in content_html:
                    fallback = fetch_content_via_requests(ch_url)
                    if fallback:
                        content_html = fallback

                if content_html:
                    f.write(process_text(content_html))
                else:
                    print(f"  警告: 无法获取章节内容，跳过")

            except Exception as e:
                print(f"  错误: {e}")
                continue

    print(f"完成: {safe_title}.txt")

# 退出驱动
driver.quit()
