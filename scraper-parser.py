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



def get_scrapeops_url(url, location="us"):
    payload = {
        "api_key": API_KEY,
        "url": url,
        "country": location,
        "wait": 5000,
        }
    proxy_url = "https://proxy.scrapeops.io/v1/?" + urlencode(payload)
    return proxy_url


## Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



@dataclass
class SearchData:
    name: str = ""
    stars: float = 0
    url: str = ""
    publisher: str = ""

    def __post_init__(self):
        self.check_string_fields()
        
    def check_string_fields(self):
        for field in fields(self):
            # Check string fields
            if isinstance(getattr(self, field.name), str):
                # If empty set default text
                if getattr(self, field.name) == "":
                    setattr(self, field.name, f"No {field.name}")
                    continue
                # Strip any trailing spaces, etc.
                value = getattr(self, field.name)
                setattr(self, field.name, value.strip())



class DataPipeline:
    
    def __init__(self, csv_filename="", storage_queue_limit=50):
        self.names_seen = []
        self.storage_queue = []
        self.storage_queue_limit = storage_queue_limit
        self.csv_filename = csv_filename
        self.csv_file_open = False
    
    def save_to_csv(self):
        self.csv_file_open = True
        data_to_save = []
        data_to_save.extend(self.storage_queue)
        self.storage_queue.clear()
        if not data_to_save:
            return

        keys = [field.name for field in fields(data_to_save[0])]
        file_exists = os.path.isfile(self.csv_filename) and os.path.getsize(self.csv_filename) > 0
        with open(self.csv_filename, mode="a", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=keys)

            if not file_exists:
                writer.writeheader()

            for item in data_to_save:
                writer.writerow(asdict(item))

        self.csv_file_open = False
                    
    def is_duplicate(self, input_data):
        if input_data.name in self.names_seen:
            logger.warning(f"Duplicate item found: {input_data.name}. Item dropped.")
            return True
        self.names_seen.append(input_data.name)
        return False
            
    def add_data(self, scraped_data):
        if self.is_duplicate(scraped_data) == False:
            self.storage_queue.append(scraped_data)
            if len(self.storage_queue) >= self.storage_queue_limit and self.csv_file_open == False:
                self.save_to_csv()
                       
    def close_pipeline(self):
        if self.csv_file_open:
            time.sleep(3)
        if len(self.storage_queue) > 0:
            self.save_to_csv()



def scrape_search_results(keyword, location, data_pipeline=None, retries=3):
    formatted_keyword = keyword.replace(" ", "+")
    url = f"https://play.google.com/store/search?q={formatted_keyword}&c=apps"
    tries = 0
    success = False
    
    while tries <= retries and not success:
        try:
            driver = webdriver.Chrome(options=OPTIONS)
            scrapeops_proxy_url = get_scrapeops_url(url, location=location)
            response = driver.get(scrapeops_proxy_url)

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
                
                search_data = SearchData(
                    name=name,
                    stars=rating,
                    url=href,
                    publisher=publisher
                )                

                data_pipeline.add_data(search_data)
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




def start_scrape(keywords, location, data_pipeline=None, max_threads=5, retries=3):
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        executor.map(
            scrape_search_results,
            keywords,
            [location] * len(keywords),
            [data_pipeline] * len(keywords),
            [retries] * len(keywords)
        )


def process_app(row, location, retries=3):
    url = row["url"]
    tries = 0
    success = False

    while tries <= retries and not success:
        try:
            driver = webdriver.Chrome(options=OPTIONS)
            driver.get(url, location=location)

            review_container = driver.find_element(By.CSS_SELECTOR, "div[data-g-id='reviews']")
            review_headers = review_container.find_elements(By.CSS_SELECTOR, "header[data-review-id]")
            for review in review_headers:
                header_text = review.text.split("\n")
                stars = review.find_element(By.CSS_SELECTOR, "div[role='img']").get_attribute("aria-label").split(" ")[1]
                name = header_text[0]
                date = header_text[2]
                description = review.find_element(By.XPATH, "..").text.split("\n")[3]
                review_data = {
                    "name": name,
                    "date": date,
                    "stars": stars,
                    "description": description
                }         
                
                print(review_data)
                
            success = True

        except Exception as e:
            logger.error(f"Exception thrown: {e}")
            logger.warning(f"Failed to process page: {row['url']}")
            logger.warning(f"Retries left: {retries-tries}")
            tries += 1

        finally:
            driver.quit()

    if not success:
        raise Exception(f"Max Retries exceeded: {retries}")
    else:
        logger.info(f"Successfully parsed: {row['url']}")


def process_results(csv_file, location, retries=3):
    logger.info(f"processing {csv_file}")
    with open(csv_file, newline="") as file:
        reader = list(csv.DictReader(file))

        for row in reader:
            process_app(row, location, retries=retries)

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
    
    crawl_pipeline = DataPipeline(csv_filename=filename)
    start_scrape(keyword_list, LOCATION, data_pipeline=crawl_pipeline, max_threads=MAX_THREADS, retries=MAX_RETRIES)
    crawl_pipeline.close_pipeline()
    logger.info(f"Crawl complete.")
    

    logger.info("Starting scrape...")
    process_results(filename, LOCATION, retries=MAX_RETRIES)
    logger.info("Scrape Complete")