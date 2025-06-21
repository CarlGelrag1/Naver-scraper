import asyncio
import os
import random
import time
from typing import List, Dict, Any
import pandas as pd
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# 设置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NaverScraper:
    def __init__(self, urls: List[str], output_dir: str = "output"):
        self.urls = urls
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/91.0.864.59"
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",

        ]

    def _get_chrome_options(self):
        options = Options()
        # options.add_argument("--headless")  # 取消headless以便观察行为
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=ko-KR")  # 设置韩语
        options.add_argument(f"user-agent={random.choice(self.user_agents)}")
        options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2,"profile.managed_default_content_settings.javascript": 1,"profile.default_content_settings.cookies": 2,"profile.managed_default_content_settings.plugins": 2,"profile.managed_default_content_settings.popups": 2,"profile.managed_default_content_settings.geolocation": 2,"profile.managed_default_content_settings.notifications": 2,})  # 禁用图片
        return options

    async def scrape_all(self):
        for url in self.urls:
            try:
                logging.info(f"开始爬取: {url}")
                await self.scrape_url(url)
                logging.info(f"成功爬取: {url}")
                # 请求之间随机延迟，模拟人类休息
                await asyncio.sleep(random.uniform(3, 6))
            except Exception as e:
                logging.error(f"爬取失败 {url}: {str(e)}")

    async def scrape_url(self, url: str):
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self._get_chrome_options())

        try:
            # 先访问Naver首页，模拟真实用户行为
            logging.info("访问Naver首页以建立会话")
            driver.get("https://www.naver.com/")
            await asyncio.sleep(random.uniform(1, 3))  # 随机延迟
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")  # 模拟轻微滚动
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # 访问目标URL
            logging.info(f"访问目标页面: {url}")
            driver.get(url)
            await asyncio.sleep(random.uniform(1, 2))  # 等待页面加载

            # 检查是否有验证码
            if "captcha" in driver.page_source.lower():
                logging.warning("检测到验证码，请手动解决")
                input("解决验证码后按回车继续...")

            # 等待商品标题加载
            title_xpath = '//*[@id="content"]/div/div[2]/div[2]/fieldset/div[1]/div[1]/h3'
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, title_xpath)))

            # 获取商品标题（作为文件名）
            product_title = driver.find_element(By.XPATH, title_xpath).text
            safe_title = "".join([c for c in product_title if c.isalpha() or c.isdigit() or c == ' ']).rstrip()

            # 获取基本商品信息
            total_rating = self._safe_get_text(driver, '//*[@id="content"]/div/div[2]/div[1]/div[2]/div[1]/strong')
            review_count = self._safe_get_text(driver, '//*[@id="content"]/div/div[2]/div[1]/div[2]/div[2]/a/strong')

            # 获取商品价格
            price_xpath = '//*[@id="content"]/div/div[2]/div[2]/fieldset/div[1]/div[2]/div/strong/span[2]'
            price = self._safe_get_text(driver, price_xpath)

            # 创建DataFrame用于存储评论数据
            reviews_data = []

            # 产品摘要行
            reviews_data.append({
                '商品标题': product_title,
                '商品链接': url,
                '商品价格': price,
                '总星级': total_rating,
                '评论数量': review_count,
                '用户名': 'TOTAL',
                '评论星级': '',
                '评论时间': '',
                '购买规格': '',
                '评论内容': f'总计 {review_count} 条评论',
                '点赞数': '',
                '图片链接': '',
                '图片数量': ''
            })

            # 滚动到评论部分，模拟用户浏览
            logging.info("滚动到评论部分")
            review_element = WebDriverWait(driver, 10.2).until(
                EC.presence_of_element_located((By.ID, "REVIEW"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", review_element)
            await asyncio.sleep(random.uniform(1, 2))  # 模拟查看时间
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")  # 滚动到底部
            await asyncio.sleep(random.uniform(0.8, 1.5))

            # 开始翻页循环
            current_page_group = 1  # 1-10, 11-20等
            more_reviews = True
            reviews_scraped = 0

            while more_reviews:
                # 处理当前组中的每一页(1-10, 11-20等)
                for page_in_group in range(1, 11):
                    actual_page = (current_page_group - 1) * 10 + page_in_group

                    # 如果不是第1页，点击页码
                    if not (current_page_group == 1 and page_in_group == 1):
                        for attempt in range(3):  # 添加重试机制
                            try:
                                page_selector = f"#REVIEW > div > div._2LvIMaBiIO > div._2g7PKvqCKe > div > div > a:nth-child({page_in_group + 1})"
                                page_button = WebDriverWait(driver, 10).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, page_selector))
                                )
                                driver.execute_script("arguments[0].click();", page_button)
                                await asyncio.sleep(random.uniform(1, 2))  # 点击后随机延迟
                                break
                            except (TimeoutException, NoSuchElementException):
                                logging.warning(f"点击第 {actual_page} 页失败，重试 {attempt + 1}/3")
                                if attempt == 2:
                                    more_reviews = False
                                    break
                                await asyncio.sleep(2)

                    if not more_reviews:
                        break

                    # 等待评论加载
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '//*[@id="REVIEW"]/div/div[3]/div[2]/ul/li'))
                        )
                    except TimeoutException:
                        logging.info(f"第 {actual_page} 页无评论，结束翻页")
                        more_reviews = False
                        break

                    # 获取当前页面上的所有评论
                    reviews = driver.find_elements(By.XPATH, '//*[@id="REVIEW"]/div/div[3]/div[2]/ul/li')
                    if not reviews:
                        more_reviews = False
                        break

                    for i, review in enumerate(reviews, 1):
                        try:
                            review_data = self._extract_review_data(driver, i, product_title, url, price)
                            reviews_data.append(review_data)
                            reviews_scraped += 1
                        except Exception as e:
                            logging.error(f"提取第 {actual_page} 页第 {i} 条评论数据时出错: {str(e)}")

                    logging.info(f"已爬取第 {actual_page} 页，总评论数: {reviews_scraped}")

                    # 模拟滚动页面
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                # 如果还有更多页面，点击下一组按钮
                if more_reviews:
                    for attempt in range(3):
                        try:
                            next_button = WebDriverWait(driver, 10).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR,
                                                            "#REVIEW > div > div._2LvIMaBiIO > div._2g7PKvqCKe > div > div > a.fAUKm1ewwo._2Ar8-aEUTq"))
                            )
                            driver.execute_script("arguments[0].click();", next_button)
                            current_page_group += 1
                            await asyncio.sleep(random.uniform(1, 2))
                            break
                        except (TimeoutException, NoSuchElementException):
                            logging.warning(f"点击下一组按钮失败，重试 {attempt + 1}/3")
                            if attempt == 2:
                                more_reviews = False

            # 将数据保存为Excel文件
            df = pd.DataFrame(reviews_data)
            excel_path = f"{self.output_dir}/{safe_title}.xlsx"
            df.to_excel(excel_path, index=False, engine='openpyxl')
            logging.info(f"已爬取商品 {product_title} 的 {reviews_scraped} 条评论，保存到 {excel_path}")

        finally:
            driver.quit()

    def _extract_review_data(self, driver, review_index: int, product_title: str, url: str, price: str) -> Dict[str, Any]:
        """提取单条评论的数据"""
        base_xpath = f'//*[@id="REVIEW"]/div/div[3]/div[2]/ul/li[{review_index}]/div/div/div/div[1]/div'

        rating_xpath = f"{base_xpath}/div[1]/div[1]/div[2]/div[1]/em"
        username_xpath = f"{base_xpath}/div[1]/div[1]/div[2]/div[2]/strong"
        date_xpath = f"{base_xpath}/div[1]/div[1]/div[2]/div[2]/span"
        specs_xpath = f"{base_xpath}/div[1]/div[1]/div[2]/div[3]"
        content_xpath = f"{base_xpath}/div[1]/div[2]/div/span[@class='_2L3vDiadT9']"
        likes_xpath = f'//*[@id="REVIEW"]/div/div[3]/div[2]/ul/li[{review_index}]/div/div/div/div[2]/div/div/div/button/span'
        image_xpath = f"{base_xpath}/div[2]/span/img"
        image_count_xpath = f"{base_xpath}/div[2]/span/span[1]"

        return {
            '商品标题': product_title,
            '商品链接': url,
            '商品价格': price,
            '总星级': self._safe_get_text(driver, '//*[@id="content"]/div/div[2]/div[1]/div[2]/div[1]/strong'),
            '评论数量': self._safe_get_text(driver, '//*[@id="content"]/div/div[2]/div[1]/div[2]/div[2]/a/strong'),
            '用户名': self._safe_get_text(driver, username_xpath),
            '评论星级': self._safe_get_text(driver, rating_xpath),
            '评论时间': self._safe_get_text(driver, date_xpath),
            '购买规格': self._safe_get_text(driver, specs_xpath),
            '评论内容': self._safe_get_text(driver, content_xpath),
            '点赞数': self._safe_get_text(driver, likes_xpath),
            '图片链接': self._safe_get_attribute(driver, image_xpath, 'src'),
            '图片数量': self._safe_get_text(driver, image_count_xpath)
        }

    def _safe_get_text(self, driver, xpath: str) -> str:
        """安全获取元素文本"""
        try:
            return driver.find_element(By.XPATH, xpath).text
        except (NoSuchElementException, TimeoutException):
            return ""

    def _safe_get_attribute(self, driver, xpath: str, attribute: str) -> str:
        """安全获取元素属性"""
        try:
            return driver.find_element(By.XPATH, xpath).get_attribute(attribute)
        except (NoSuchElementException, TimeoutException):
            return ""

async def main():
    print("请输入要爬取的Naver商品链接，每行一个链接，输入空行结束:")
    urls = []
    while True:
        url = input()
        if not url:
            break
        urls.append(url)

    if not urls:
        print("未输入链接，程序退出")
        return

    scraper = NaverScraper(urls)
    await scraper.scrape_all()

if __name__ == "__main__":
    asyncio.run(main())
