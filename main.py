import sys
import click
import pandas as pd
import logging
from pathlib import Path
from scraper.config import config
from scraper.browser_scraper import BrowserScraper
from scraper.parser import parse_property
from dotenv import load_dotenv

load_dotenv()

Path("data").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scraper.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


@click.command()
@click.option("--pages", default=3, help="Number of pages to scrape (max 50)")
@click.option("--proxy", default=None, help="Proxy URL (e.g. http://user:pass@host:port)")
@click.option("--output", default="data/noida_buy.csv", help="Output CSV path")
@click.option("--url", default=None, help="Custom 99acres search URL")
def scrape(pages: int, proxy: str | None, output: str, url: str | None):
    search_url = url or config.search_url
    logger.info(f"Starting scrape: {search_url} | pages={pages}")

    try:
        browser = BrowserScraper(proxy=proxy)
        raw_listings = browser.scrape(search_url, max_pages=pages)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)
        sys.exit(1)

    all_properties = []
    parse_errors = 0
    for raw in raw_listings:
        parsed = parse_property(raw)
        if parsed:
            all_properties.append(parsed.model_dump())
        else:
            parse_errors += 1

    if parse_errors:
        logger.warning(f"Could not parse {parse_errors} listings (check logs for details)")

    if all_properties:
        df = pd.DataFrame(all_properties)
        df.to_csv(output, index=False)

        json_path = output.replace(".csv", ".json")
        df.to_json(json_path, orient="records", indent=2, force_ascii=False)

        logger.info(f"Saved {len(all_properties)} properties ({len(df.columns)} columns) -> {output}")

        preview = ["listing_id", "title", "price_label", "city", "bedrooms"]
        preview = [c for c in preview if c in df.columns]
        logger.info(f"\n{df[preview].head(5).to_string()}")
    else:
        logger.warning(
            "No properties scraped. Possible causes:\n"
            "  - CAPTCHA was not solved in the browser window\n"
            "  - 99acres blocked the request (try with --proxy)\n"
            "  - The search URL returns no results"
        )
        pd.DataFrame().to_csv(output, index=False)


if __name__ == "__main__":
    scrape()
