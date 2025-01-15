import os
import csv
import json
import logging
from urllib.parse import urlencode
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.common.by import By
from dataclasses import dataclass, field, fields, asdict

API_KEY = ""

OPTIONS = webdriver.ChromeOptions()
OPTIONS.add_argument("--headless")
OPTIONS.add_argument("--disable-javascript")

with open("config.json", "r") as config_file:
    config = json.load(config_file)
    API_KEY = config["api_key"]


## Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def scrape_search_results(keyword, location, retries=3):
    formatted_keyword = keyword.replace(" ", "+")
    url = f"https://play.google.com/store/search?q={formatted_keyword}&c=apps"
    tries = 0
    success = False
    
    while tries <= retries and not success:
        try:
            driver = webdriver.Chrome(options=OPTIONS)
            response = driver.get(url)

            div_cards = driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")

            Excluded_words = ["Apps & games", "Movies & TV", "Books"]
            for div_card in div_cards:
                if div_card.text in Excluded_words:
                    continue
                info_rows = div_card.find_elements(By.CSS_SELECTOR, "div div span")
                
                name = info_rows[1].text
                publisher = info_rows[2].text
                href = div_card.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                rating = 0.0
                if info_rows[3].text != None:
                    rating = info_rows[3].text
                
                search_data = {
                    "name": name,
                    "stars": rating,
                    "url": href,
                    "publisher": publisher
                }             

                print(search_data)
            logger.info(f"Successfully parsed data from: {url}")
            success = True        
                    
        except Exception as e:
            logger.error(f"An error occurred while processing page {url}: {e}")
            logger.info(f"Retrying request for page: {url}, retries left {retries-tries}")
            tries+=1
            
        finally:
            driver.quit()
    if not success:
        raise Exception(f"Max Retries exceeded: {retries}")

def start_scrape(keywords, location, retries=3):
    for keyword in keywords:
        scrape_search_results(keyword, location, retries=retries)


if __name__ == "__main__":

    MAX_RETRIES = 3
    MAX_THREADS = 5
    
    LOCATION = "us"

    logger.info(f"Crawl starting...")

    ## INPUT ---> List of keywords to scrape
    keyword_list = ["crypto wallet"]
    aggregate_files = []

    ## Job Processes
    filename = "report.csv"
    
    start_scrape(keyword_list, LOCATION, retries=MAX_RETRIES)
    logger.info(f"Crawl complete.")