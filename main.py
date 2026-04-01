import sys
import click
import pandas as pd
import logging
import json
import time
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
        logging.FileHandler("logs/scraper.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


class IncrementalSaver:
    """Parses raw listings and writes CSV+JSON after every page.

    Output files always contain the latest data -- if the process dies at
    any point, the files on disk are complete up to the last successful page.
    """

    def __init__(self, output_path: str):
        self.output_csv = Path(output_path)
        self.output_json = Path(output_path.replace(".csv", ".json"))
        self.parsed: list[dict] = []
        self.parsed_ids: set[str] = set()
        self.parse_errors = 0
        self._last_save_count = 0

    def load_existing(self):
        """Load previously saved output (for resume mode)."""
        if self.output_csv.exists():
            try:
                df = pd.read_csv(self.output_csv)
                if not df.empty and "listing_id" in df.columns:
                    self.parsed = df.to_dict(orient="records")
                    self.parsed_ids = {str(r["listing_id"]) for r in self.parsed if r.get("listing_id")}
                    self._last_save_count = len(self.parsed)
                    logger.info(f"Loaded {len(self.parsed)} existing parsed listings from {self.output_csv}")
            except Exception as e:
                logger.warning(f"Could not load existing output: {e}")

    def process_raw(self, raw_listings: list[dict]):
        """Parse new raw listings and add to the buffer."""
        for raw in raw_listings:
            parsed = parse_property(raw)
            if not parsed:
                self.parse_errors += 1
                continue
            lid = str(parsed.listing_id) if parsed.listing_id else None
            if lid and lid in self.parsed_ids:
                continue
            if lid:
                self.parsed_ids.add(lid)
            self.parsed.append(parsed.model_dump())

    def save(self):
        """Write CSV + JSON to disk. Safe to call repeatedly."""
        if not self.parsed or len(self.parsed) == self._last_save_count:
            return
        df = pd.DataFrame(self.parsed)
        df.to_csv(self.output_csv, index=False)
        df.to_json(self.output_json, orient="records", indent=2, force_ascii=False)
        self._last_save_count = len(self.parsed)

    def on_page_done(self, results: list[dict], seen_ids: set[str], page_num: int):
        """Callback from BrowserScraper -- parse new results and save immediately."""
        new_raw = results[len(self.parsed) + self.parse_errors:]
        if new_raw:
            self.process_raw(new_raw)
            self.save()

    def finalize(self):
        """Final save + summary log."""
        self.save()
        if self.parse_errors:
            logger.warning(f"Could not parse {self.parse_errors} listings (check logs)")
        if self.parsed:
            df = pd.DataFrame(self.parsed)
            logger.info(f"Output: {len(self.parsed)} properties ({len(df.columns)} cols) -> {self.output_csv}")
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


@click.command()
@click.option("--pages", default=3, help="Number of pages to scrape (max 500)")
@click.option("--proxy", default=None, help="Proxy URL (e.g. http://user:pass@host:port)")
@click.option("--output", default="data/noida_buy.csv", help="Output CSV path")
@click.option("--url", default=None, help="Custom 99acres search URL")
@click.option("--resume", is_flag=True, default=False, help="Resume from last checkpoint")
def scrape(pages: int, proxy: str | None, output: str, url: str | None, resume: bool):
    search_url = url or config.search_url

    logger.info("=" * 60)
    if resume:
        logger.info(f"RESUMING scrape: {search_url}")
    else:
        logger.info(f"STARTING scrape: {search_url}")
    logger.info(f"Pages: {pages} | Output: {output}")
    logger.info("=" * 60)

    saver = IncrementalSaver(output)
    if resume:
        saver.load_existing()

    browser = BrowserScraper(proxy=proxy)
    browser.set_page_callback(saver.on_page_done)

    raw_listings = []
    interrupted = False
    start = time.time()

    try:
        raw_listings = browser.scrape(search_url, max_pages=pages, resume=resume)
    except KeyboardInterrupt:
        logger.info("Interrupted by user -- saving collected data.")
        interrupted = True
    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)
        interrupted = True

    # Final parse of any remaining raw data not yet processed
    saver.process_raw(raw_listings)
    saver.finalize()

    elapsed = time.time() - start

    if interrupted:
        logger.info(
            f"Partial run: {len(saver.parsed)} listings saved in {elapsed/60:.1f}min.\n"
            f"  Run with --resume to continue: python main.py --pages {pages} --resume"
        )
        sys.exit(1)
    else:
        logger.info(f"Complete: {len(saver.parsed)} listings in {elapsed/60:.1f}min.")


if __name__ == "__main__":
    scrape()
