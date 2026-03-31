import click
import pandas as pd
import json
import logging
from pathlib import Path
from scraper.config import config
from scraper.api_client import ApiClient
from scraper.parser import parse_property
from scraper.browser_scraper import BrowserScraper
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/scraper.log"), logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

@click.command()
@click.option("--pages", default=0, help="Max pages (0 = all)")
@click.option("--proxy", default=None, help="Proxy URL")
@click.option("--output", default="data/99acres_noida.csv", help="Output file")
@click.option("--fallback", is_flag=True, help="Force Playwright fallback")
def scrape(pages: int, proxy: str | None, output: str, fallback: bool):
    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    
    all_properties = []
    client = ApiClient(proxy=proxy)
    
    if fallback:
        logger.warning("Forcing browser fallback (slow)")
        browser = BrowserScraper()
        data = browser.scrape(config.search_url, max_pages=pages or 10)
        all_properties.extend(data)
    else:
        page = 1
        while True:
            try:
                result = client.get_listings(page)
                for raw in result["listings"]:
                    parsed = parse_property(raw)
                    if parsed:
                        all_properties.append(parsed.model_dump())
                
                if not result.get("has_more") or (pages and page >= pages):
                    break
                    
                page += 1
                
            except Exception as e:
                logger.error(f"Page {page} failed: {e}. Switching to browser fallback...")
                fallback_scraper = BrowserScraper()
                all_properties.extend(fallback_scraper.scrape(config.search_url, max_pages=3))
                break
    
    # Save
    df = pd.DataFrame(all_properties)
    df.to_csv(output, index=False)
    df.to_json(output.replace(".csv", ".json"), orient="records", indent=2)
    
    logger.info(f"Scraped {len(all_properties)} properties -> {output}")

if __name__ == "__main__":
    scrape()