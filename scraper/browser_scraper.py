from playwright.sync_api import sync_playwright, Page
from playwright_stealth import Stealth
import logging
import json
import re
import random
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PAGES_HARD_LIMIT = 50
BASE_PAGE_DELAY = (4, 7)
BACKOFF_INCREMENT = (1, 3)

_LISTING_ID_KEYS = ("PROP_ID", "propId", "id", "propertyId", "prop_id", "SPID")
_LISTING_SENTINEL_KEYS = ("PROP_ID", "propId", "PRICE", "price", "LOCALITY_NAME", "LOCALITY")
_LISTING_CONTAINER_KEYS = (
    "properties", "srpResults", "listings", "data",
    "newProjects", "searchResults", "tuples", "pageProps",
)
_SKIP_URL_PATTERNS = (
    "recommended-projects", "discovery/", "autocomplete",
    "trending", "banner", "widget", "notification", "tracking",
)


class BrowserScraper:
    def __init__(self, proxy: str | None = None):
        self.proxy = proxy

    def _human_behave(self, page: Page):
        """Simulate natural browsing: random scroll + mouse movement."""
        for _ in range(random.randint(2, 4)):
            page.mouse.move(
                random.randint(200, 1200),
                random.randint(100, 600),
                steps=random.randint(8, 20),
            )
            page.wait_for_timeout(random.randint(150, 400))
            scroll_pct = random.uniform(0.3, 0.7)
            page.evaluate(f"window.scrollBy(0, window.innerHeight * {scroll_pct})")
            page.wait_for_timeout(random.randint(500, 1000))
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(random.randint(800, 1500))

    def _looks_like_listing(self, item: dict) -> bool:
        return isinstance(item, dict) and any(k in item for k in _LISTING_SENTINEL_KEYS)

    def _extract_listings_deep(self, data) -> list[dict]:
        if isinstance(data, list) and data and self._looks_like_listing(data[0]):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            for key in _LISTING_CONTAINER_KEYS:
                val = data.get(key)
                if val is not None:
                    result = self._extract_listings_deep(val)
                    if result:
                        return result
            for val in data.values():
                if isinstance(val, (dict, list)):
                    result = self._extract_listings_deep(val)
                    if result:
                        return result
        return []

    def _extract_from_scripts(self, page: Page) -> list[dict]:
        try:
            scripts = page.evaluate(
                "() => Array.from(document.querySelectorAll('script'))"
                ".map(s => s.textContent).filter(t => t && t.length > 500)"
            )
        except Exception:
            return []

        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*</script',
            r'window\.__NEXT_DATA__\s*=\s*({.+?});\s*</script',
            r'"srpResults"\s*:\s*(\[.+?\])\s*[,}]',
            r'"properties"\s*:\s*(\[.+?\])\s*[,}]',
        ]
        for text in scripts:
            for pat in patterns:
                m = re.search(pat, text, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(1))
                        found = self._extract_listings_deep(obj) if isinstance(obj, dict) else (
                            obj if isinstance(obj, list) and obj and self._looks_like_listing(obj[0]) else []
                        )
                        if found:
                            logger.info(f"Extracted {len(found)} listings from embedded script")
                            return found
                    except json.JSONDecodeError:
                        continue
            try:
                obj = json.loads(text.strip())
                found = self._extract_listings_deep(obj)
                if found:
                    logger.info(f"Extracted {len(found)} listings from script JSON blob")
                    return found
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    def _extract_from_dom(self, page: Page) -> list[dict]:
        try:
            return page.evaluate("""() => {
                const results = [];
                const sels = [
                    '[id^="srp_tuple_"]', '.srpTuple__tupleTable',
                    '.projectTuple__projectContent', '.tupleNew__outerTupleWrap',
                    '.nb__cardWrapper', '[class*="tuple"]', '[class*="Tuple"]',
                    '[class*="srpCard"]', '[class*="property-card"]',
                ];
                let cards = [];
                for (const s of sels) {
                    const found = document.querySelectorAll(s);
                    if (found.length > cards.length) cards = Array.from(found);
                }
                for (const card of cards) {
                    try {
                        const t = card.textContent || '';
                        let propUrl = '', title = '';
                        for (const a of card.querySelectorAll('a[href]')) {
                            const h = a.getAttribute('href') || '';
                            if (h.includes('99acres') || h.startsWith('/')) {
                                if (!propUrl || a.textContent.length > title.length) {
                                    propUrl = h; title = (a.textContent || '').trim();
                                }
                            }
                        }
                        let propId = '';
                        const tid = card.getAttribute('id') || '';
                        const idm = tid.match(/\\d+/);
                        if (idm) propId = idm[0];
                        if (!propId && propUrl) {
                            const um = propUrl.match(/(\\d{6,})/);
                            if (um) propId = um[1];
                        }
                        let price = '';
                        const pm = t.match(/\\u20B9[\\s]?[\\d.,]+\\s*(Lac|Cr|L|K|Lakh|Crore)?/i);
                        if (pm) price = pm[0].trim();
                        if (propId || title || price) {
                            results.push({
                                PROP_ID: propId, title, PRICE: price,
                                LOCALITY_NAME: '', propUrl, _source: 'dom',
                            });
                        }
                    } catch(e) {}
                }
                return results;
            }""")
        except Exception as e:
            logger.debug(f"DOM extraction error: {e}")
            return []

    def _url_with_page(self, base: str, page_num: int) -> str:
        parsed = urlparse(base)
        q = dict(parse_qsl(parsed.query, keep_blank_values=True))
        q["page"] = str(page_num)
        return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

    def _get_prop_id(self, raw: dict) -> str:
        for k in _LISTING_ID_KEYS:
            v = raw.get(k)
            if v:
                return str(v)
        return ""

    def _is_blocked(self, html: str) -> bool:
        lower = html.lower()
        return "access denied" in lower or len(html) < 1000

    def _is_captcha(self, html: str) -> bool:
        lower = html.lower()
        return any(kw in lower for kw in ("captcha", "verify you are human", "robot check"))

    def _wait_for_human(self, page: Page, reason: str, timeout_ms: int = 180_000):
        logger.warning(
            f"{reason}\n"
            "  The browser window is open -- please resolve manually.\n"
            f"  Waiting up to {timeout_ms // 1000}s..."
        )
        page.wait_for_timeout(timeout_ms)

    def scrape(self, url: str, max_pages: int = 5) -> list[dict]:
        max_pages = min(max_pages, MAX_PAGES_HARD_LIMIT)
        stealth = Stealth()

        browser = None
        try:
            pw_ctx = stealth.use_sync(sync_playwright())
            pw = pw_ctx.__enter__()

            Path("data").mkdir(exist_ok=True)
            Path("logs").mkdir(exist_ok=True)

            browser = pw.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                ],
            )

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
                proxy={"server": self.proxy} if self.proxy else None,
                locale="en-US",
                timezone_id="Asia/Kolkata",
            )

            page = context.new_page()

            captured_listings: list[dict] = []

            def on_response(resp):
                try:
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct or "99acres.com" not in resp.url:
                        return
                    if any(pat in resp.url.lower() for pat in _SKIP_URL_PATTERNS):
                        return
                    body = resp.json()
                    if isinstance(body, dict):
                        found = self._extract_listings_deep(body)
                        if found:
                            captured_listings.extend(found)
                            logger.info(f"XHR captured {len(found)} listings from {resp.url[:80]}")
                except Exception:
                    pass

            page.on("response", on_response)

            results: list[dict] = []
            seen_ids: set[str] = set()
            consecutive_empty = 0

            for p_num in range(1, max_pages + 1):
                logger.info(f"Scraping page {p_num}/{max_pages}")
                captured_listings.clear()

                target_url = self._url_with_page(url, p_num)

                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
                except Exception as e:
                    logger.error(f"Navigation failed on page {p_num}: {e}")
                    break

                # Randomized wait that increases slightly with page number
                base_lo, base_hi = BASE_PAGE_DELAY
                inc_lo, inc_hi = BACKOFF_INCREMENT
                extra = min(p_num - 1, 10) * random.uniform(inc_lo, inc_hi)
                wait_sec = random.uniform(base_lo, base_hi) + extra
                page.wait_for_timeout(int(wait_sec * 1000))

                html = page.content()

                if self._is_blocked(html):
                    self._wait_for_human(page, "Access denied by Akamai WAF.", 60_000)
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
                        page.wait_for_timeout(5000)
                        html = page.content()
                        if self._is_blocked(html):
                            logger.error("Still blocked after retry. Stopping.")
                            break
                    except Exception:
                        break

                if self._is_captcha(html):
                    self._wait_for_human(page, "CAPTCHA detected!")

                self._human_behave(page)

                # --- Extraction pipeline ---
                raw_listings: list[dict] = list(captured_listings)

                script_listings = self._extract_from_scripts(page)
                if script_listings:
                    raw_listings.extend(script_listings)

                if not raw_listings:
                    raw_listings = self._extract_from_dom(page)

                if not raw_listings:
                    consecutive_empty += 1
                    logger.warning(f"No listings on page {p_num} (empty streak: {consecutive_empty})")
                    try:
                        page.screenshot(path=f"logs/browser_page_{p_num}.png", full_page=True)
                    except Exception:
                        pass
                    if consecutive_empty >= 2:
                        logger.warning("2 consecutive empty pages -- stopping.")
                        break
                    continue

                consecutive_empty = 0
                new_count = 0
                for raw in raw_listings:
                    if not isinstance(raw, dict):
                        continue
                    pid = self._get_prop_id(raw)
                    if not pid:
                        continue
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    results.append(raw)
                    new_count += 1

                logger.info(f"Page {p_num}: {new_count} new unique ({len(results)} total)")

                if new_count == 0 and p_num > 1:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        logger.info("No new listings for 2 pages -- end of results.")
                        break

            logger.info(f"Scraper finished: {len(results)} unique listings collected")
            return results

        except Exception as e:
            logger.error(f"Scraper crashed: {e}", exc_info=True)
            return []

        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                pw_ctx.__exit__(None, None, None)
            except Exception:
                pass
