from playwright.sync_api import sync_playwright
from .parser import parse_property
import logging
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from pathlib import Path

logger = logging.getLogger(__name__)

class BrowserScraper:
    def scrape(self, url: str, max_pages: int = 5):
        with sync_playwright() as p:
            Path("data").mkdir(exist_ok=True)
            storage_path = Path("data") / "playwright_storage.json"

            # Use saved session if available; otherwise run headful for manual verification.
            headless = storage_path.exists()
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                storage_state=str(storage_path) if storage_path.exists() else None,
            )
            page = context.new_page()
            
            def _url_with_page(base: str, page_num: int) -> str:
                parsed = urlparse(base)
                q = dict(parse_qsl(parsed.query, keep_blank_values=True))
                q["page"] = str(page_num)
                new_query = urlencode(q, doseq=True)
                return urlunparse(parsed._replace(query=new_query))

            def _extract_listings(payload: dict) -> list[dict]:
                # Keep in sync with ApiClient.get_listings() robust key detection
                listings = (
                    payload.get("properties")
                    or payload.get("srpResults")
                    or payload.get("data")
                    or payload.get("listings")
                    or payload.get("newProjects")
                    or []
                )
                return listings if isinstance(listings, list) else []

            # Capture JSON responses that contain listing arrays while the page loads.
            captured_payloads: list[dict] = []

            def on_response(resp):
                try:
                    rurl = resp.url.lower()
                    if "99acres.com" not in rurl:
                        return
                    # The listings JSON is often fetched from api-aggregator during page load.
                    if "/api-aggregator/" not in rurl and "api-aggregator" not in rurl:
                        return
                    # Don't rely only on content-type; attempt JSON parse.
                    data = resp.json()
                    if isinstance(data, dict) and _extract_listings(data):
                        captured_payloads.append(data)
                except Exception:
                    # Best-effort capture; ignore parse failures.
                    return

            page.on("response", on_response)

            results: list[dict] = []
            seen_ids: set[str] = set()

            for p_num in range(1, max_pages + 1):
                logger.info(f"Browser scraping page {p_num}")
                captured_payloads.clear()

                target_url = _url_with_page(url, p_num)

                # Explicitly wait for the listings endpoint response during navigation.
                try:
                    with page.expect_response(
                        lambda r: ("api-aggregator/srp/search" in r.url.lower())
                        and ("99acres.com" in r.url.lower()),
                        timeout=20000,
                    ) as resp_info:
                        page.goto(target_url, wait_until="domcontentloaded")
                    resp = resp_info.value
                    logger.info(f"Intercepted listings response: {resp.status} {resp.url}")
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and _extract_listings(data):
                            captured_payloads.append(data)
                    except Exception:
                        pass
                except Exception:
                    # Fall back to normal navigation and passive response capture.
                    page.goto(target_url, wait_until="domcontentloaded")

                page.wait_for_timeout(5000)

                # A bit of scrolling helps trigger lazy network calls on some pages.
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                raw_listings: list[dict] = []
                for payload in captured_payloads:
                    raw_listings.extend(_extract_listings(payload))

                # If we didn't capture any JSON, break early (likely blocked/captcha/selector change).
                if not raw_listings:
                    try:
                        page.screenshot(path=f"logs/browser_page_{p_num}.png", full_page=True)
                        logger.warning(f"No JSON listings captured. Screenshot saved to logs/browser_page_{p_num}.png")
                        html = page.content().lower()
                        if "captcha" in html or "verify" in html or "robot" in html:
                            logger.warning(
                                "Blocked by bot-check/captcha. "
                                "A browser window should be open — solve the captcha once, "
                                "then re-run the command to reuse the saved session."
                            )

                            # Give time for manual solve on first run (no storage yet).
                            if not storage_path.exists():
                                page.wait_for_timeout(180000)  # 3 minutes
                    except Exception:
                        pass
                    break

                for raw in raw_listings:
                    parsed = parse_property(raw if isinstance(raw, dict) else {})
                    if not parsed:
                        continue
                    if parsed.prop_id and parsed.prop_id in seen_ids:
                        continue
                    if parsed.prop_id:
                        seen_ids.add(parsed.prop_id)
                    results.append(parsed.model_dump())
                    
            browser.close()
            # Save session if we managed to load anything (so next runs can be headless).
            try:
                if results and not storage_path.exists():
                    context.storage_state(path=str(storage_path))
                    logger.info(f"Saved session storage to {storage_path}")
            except Exception:
                pass
            return results