from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import time
import re
import os

#处理爬取到的HTML文本
def process_text(html_content):
    processed = re.sub(r'(?i)</\s*p\s*>', '\n', html_content)
    processed = re.sub(r'<[^>]+>', '', processed)
    processed = re.sub(r'\n+', '\n', processed).strip()
    return processed

#处理文件名中的特殊字符
def sanitize_filename(filename):
    # 替换Windows文件系统不允许的字符
    invalid_chars = r'[\\/:*?"<>|]'
    # 替换为下划线
    sanitized = re.sub(invalid_chars, '_', filename)
    # 移除前后的空白字符
    sanitized = sanitized.strip()
    return sanitized

#输入小说的目录页网址
URL = input("请输入小说的目录页网址(多个网址请用空格分隔):")
urls = [url.strip() for url in URL.split()]

#驱动配置
options = Options()
# 反自动化检测
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_experimental_option('excludeSwitches', ['enable-automation'])
options.add_experimental_option('useAutomationExtension', False)
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0')
# CI环境下使用headless模式
if os.environ.get('CI'):
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
driver = webdriver.Edge(options=options)
# 移除 navigator.webdriver 标记
driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
})
wait = WebDriverWait(driver, 30)


for url in urls:
    driver.get(url)
    time.sleep(3)
    # 调试：打印实际加载的页面信息
    print(f"Page URL: {driver.current_url}")
    print(f"Page title: {driver.title}")
    #爬取标题
    book_title_xpath = '/html/body/div[2]/div[3]/div[1]/h1'
    try:
        book_title = wait.until(EC.presence_of_element_located((By.XPATH, book_title_xpath))).text
    except Exception:
        print("Failed to find book title element. Page source (first 2000 chars):")
        print(driver.page_source[:2000])
        raise
    #处理文件名中的特殊字符
    safe_title = sanitize_filename(book_title)
    #没有可爬取内容时结束任务
    try:
        with open('novel/' + safe_title + '.txt', "w+", encoding='utf-8') as f:
            #进入轻小说开始页
            first_part_xpath = '/html/body/div[2]/div[3]/div[2]/div[2]/div/ul/li[1]/a'
            begin_button = wait.until(EC.element_to_be_clickable((By.XPATH, first_part_xpath)))
            begin_button.click()
            #开始爬取每页内容
            while True:
                #爬取章节标题
                part_title_xpath = '//*[@id="mlfy_main_text"]/h1'
                part_title = wait.until(EC.presence_of_element_located((By.XPATH, part_title_xpath))).text
                f.write('\n' + part_title + '\n\n')
                #爬取章节内容
                article_xpath='//*[@id="TextContent"]'
                article = wait.until(EC.presence_of_element_located((By.XPATH, article_xpath))).text
                f.write(process_text(article))
                #进入下一页
                next_part_xpath = '//*[@id="readbg"]/p/a[5]'
                button = wait.until(EC.element_to_be_clickable((By.XPATH, next_part_xpath)))
                #随机等待,反爬虫
                time.sleep(random.randint(0, 2))
                button.click()
                time.sleep(1)
    except NoSuchElementException:
        pass
#退出驱动
driver.quit()