from playwright.sync_api import sync_playwright, Page
from playwright_stealth import Stealth
import logging
import json
import re
import random
import time
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PAGES_HARD_LIMIT = 500
BASE_PAGE_DELAY = (5, 9)
BACKOFF_INCREMENT = (0.5, 1.5)
CHECKPOINT_FILE = Path("data") / "_checkpoint.json"
COOKIES_FILE = Path("data") / "_cookies.json"

# Every BATCH_SIZE pages, take a long human-like break
BATCH_SIZE = 25
BATCH_BREAK_RANGE = (60, 120)

# After this many consecutive pages with 0 new listings, stop
MAX_CONSECUTIVE_EMPTY = 5

_LISTING_ID_KEYS = ("SPID", "PROP_ID", "propId", "id", "propertyId", "prop_id")
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
        self._on_page_done = None

    def set_page_callback(self, fn):
        """Register a callback fn(results, seen_ids, page_num) called after every page."""
        self._on_page_done = fn

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def _save_checkpoint(self, results: list[dict], seen_ids: set[str], last_page: int, url: str):
        try:
            payload = {
                "url": url,
                "last_page": last_page,
                "seen_ids": list(seen_ids),
                "results": results,
            }
            tmp = CHECKPOINT_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, default=str, ensure_ascii=False), encoding="utf-8")
            tmp.replace(CHECKPOINT_FILE)
        except Exception as e:
            logger.debug(f"Checkpoint save failed: {e}")

    def _load_checkpoint(self, url: str) -> tuple[list[dict], set[str], int]:
        try:
            if not CHECKPOINT_FILE.exists():
                return [], set(), 0
            data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
            if data.get("url") != url:
                logger.info("Checkpoint URL mismatch -- starting fresh")
                return [], set(), 0
            results = data.get("results", [])
            seen_ids = set(data.get("seen_ids", []))
            last_page = data.get("last_page", 0)
            logger.info(f"Resumed from checkpoint: {len(results)} listings, page {last_page} completed")
            return results, seen_ids, last_page
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")
            return [], set(), 0

    def clear_checkpoint(self):
        try:
            CHECKPOINT_FILE.unlink(missing_ok=True)
            CHECKPOINT_FILE.with_suffix(".tmp").unlink(missing_ok=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cookie persistence -- solve CAPTCHA once, reuse across restarts
    # ------------------------------------------------------------------

    def _save_cookies(self, context):
        try:
            cookies = context.cookies()
            COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load_cookies(self, context):
        try:
            if COOKIES_FILE.exists():
                cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
                context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} saved cookies (CAPTCHA session reused)")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Human-like behavior
    # ------------------------------------------------------------------

    def _human_behave(self, page: Page):
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

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

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
            data = page.evaluate("""() => {
                try {
                    const d = window.__initialData__;
                    if (d && d.srp && d.srp.pageData && d.srp.pageData.properties) {
                        return d.srp.pageData.properties;
                    }
                    if (d && d.pageData && d.pageData.properties) {
                        return d.pageData.properties;
                    }
                } catch(e) {}
                try {
                    const n = window.__NEXT_DATA__;
                    if (n && n.props) return null;
                } catch(e) {}
                try {
                    const s = window.__INITIAL_STATE__;
                    if (s) return null;
                } catch(e) {}
                return null;
            }""")
            if data and isinstance(data, list) and len(data) > 0 and self._looks_like_listing(data[0]):
                logger.info(f"Extracted {len(data)} listings from window.__initialData__")
                return data
        except Exception:
            pass

        try:
            scripts = page.evaluate(
                "() => Array.from(document.querySelectorAll('script'))"
                ".map(s => s.textContent).filter(t => t && t.length > 500)"
            )
        except Exception:
            return []

        patterns = [
            r'window\.__initialData__\s*=\s*({.+})',
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'window\.__NEXT_DATA__\s*=\s*({.+?});',
        ]
        for text in scripts:
            for pat in patterns:
                m = re.search(pat, text, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(1))
                        found = self._extract_listings_deep(obj)
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
                    '.nb__cardWrapper', '[class*="srpCard"]', '[class*="property-card"]',
                ];
                let cards = [];
                for (const s of sels) {
                    const found = document.querySelectorAll(s);
                    if (found.length > cards.length) cards = Array.from(found);
                }
                if (!cards.length) {
                    const tupleCards = document.querySelectorAll('[class*="tuple"], [class*="Tuple"]');
                    if (tupleCards.length) cards = Array.from(tupleCards);
                }
                for (const card of cards) {
                    try {
                        const t = card.textContent || '';
                        let propUrl = '', title = '';
                        for (const a of card.querySelectorAll('a[href]')) {
                            const h = a.getAttribute('href') || '';
                            if (h.includes('99acres') || h.startsWith('/')) {
                                if (!propUrl || a.textContent.length > title.length) {
                                    propUrl = h;
                                    title = (a.textContent || '').trim();
                                }
                            }
                        }
                        let propId = '';
                        if (propUrl) {
                            const spidMatch = propUrl.match(/spid-[A-Z]?(\\d{6,})/i);
                            if (spidMatch) propId = spidMatch[1];
                        }
                        if (!propId) {
                            const tid = card.getAttribute('id') || '';
                            const idm = tid.match(/(\\d{6,})/);
                            if (idm) propId = idm[1];
                        }
                        if (!propId && propUrl) {
                            const um = propUrl.match(/(\\d{6,})/);
                            if (um) propId = um[1];
                        }
                        if (!propId) continue;
                        let price = '';
                        const pm = t.match(/\\u20B9[\\s]?[\\d.,]+\\s*(Lac|Cr|L|K|Lakh|Crore)?/i);
                        if (pm) price = pm[0].trim();
                        let bedrooms = '';
                        const bhkMatch = t.match(/(\\d+)\\s*BHK/i);
                        if (bhkMatch) bedrooms = bhkMatch[1];
                        let area = '';
                        const areaMatch = t.match(/(\\d[\\d,.]*)\\s*sq\\.?\\s*ft/i);
                        if (areaMatch) area = areaMatch[1].replace(/,/g, '');
                        let locality = '';
                        if (propUrl) {
                            const parts = propUrl.split('/').pop() || '';
                            const locMatch = parts.match(/in-(.+?)-\\d/);
                            if (locMatch) {
                                locality = locMatch[1].replace(/-/g, ' ')
                                    .replace(/\\b\\w/g, c => c.toUpperCase());
                            }
                        }
                        let propType = '';
                        if (/apartment|flat/i.test(t)) propType = 'Residential Apartment';
                        else if (/villa/i.test(t)) propType = 'Villa';
                        else if (/plot|land/i.test(t)) propType = 'Plot';
                        else if (/house/i.test(t)) propType = 'House';
                        else if (/penthouse/i.test(t)) propType = 'Penthouse';
                        else if (/studio/i.test(t)) propType = 'Studio';
                        let bathrooms = '';
                        const bathMatch = t.match(/(\\d+)\\s*bath/i);
                        if (bathMatch) bathrooms = bathMatch[1];
                        let floorNum = '';
                        const floorMatch = t.match(/(\\d+)(?:st|nd|rd|th)?\\s*floor/i);
                        if (floorMatch) floorNum = floorMatch[1];
                        let fullUrl = propUrl;
                        if (propUrl && !propUrl.startsWith('http')) {
                            fullUrl = 'https://www.99acres.com' + (propUrl.startsWith('/') ? '' : '/') + propUrl;
                        }
                        results.push({
                            PROP_ID: propId, SPID: propId, PROP_HEADING: title, PRICE: price,
                            LOCALITY: locality, PD_URL: fullUrl, BEDROOM_NUM: bedrooms,
                            BATHROOM_NUM: bathrooms, PROPERTY_TYPE: propType, FLOOR_NUM: floorNum,
                            SUPERBUILTUP_SQFT: area, _source: 'dom',
                        });
                    } catch(e) {}
                }
                return results;
            }""")
        except Exception as e:
            logger.debug(f"DOM extraction error: {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _url_with_page(self, base: str, page_num: int) -> str:
        parsed = urlparse(base)
        q = dict(parse_qsl(parsed.query, keep_blank_values=True))
        q["page"] = str(page_num)
        return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))

    def _get_prop_id(self, raw: dict) -> str:
        for k in _LISTING_ID_KEYS:
            v = raw.get(k)
            if v:
                s = str(v).strip()
                if k == "SPID" and s.isdigit() and len(s) >= 5:
                    return s
                m = re.match(r'^[A-Z]?(\d{5,})$', s)
                if m:
                    return m.group(1)
                if s.isdigit() and len(s) >= 5:
                    return s
        return ""

    def _is_blocked(self, html: str) -> bool:
        return "access denied" in html.lower() or len(html) < 1000

    def _is_captcha(self, html: str) -> bool:
        lower = html.lower()
        return any(kw in lower for kw in ("captcha", "verify you are human", "robot check"))

    def _wait_for_human(self, page: Page, context, reason: str, timeout_ms: int = 300_000):
        logger.warning(
            f"{reason}\n"
            "  >>> Solve it in the browser window -- scraper will continue automatically.\n"
            f"  >>> Waiting up to {timeout_ms // 1000}s..."
        )
        page.wait_for_timeout(timeout_ms)
        self._save_cookies(context)

    def _wait_for_xhr(self, pool: list[dict], timeout_sec: float = 8.0):
        initial_len = len(pool)
        start = time.time()
        while time.time() - start < timeout_sec:
            if len(pool) > initial_len:
                return
            time.sleep(0.3)

    def _batch_break(self, page: Page, p_num: int):
        """Take a long human-like break every BATCH_SIZE pages."""
        if p_num % BATCH_SIZE != 0:
            return
        lo, hi = BATCH_BREAK_RANGE
        wait = random.uniform(lo, hi)
        logger.info(
            f"--- Batch break after {p_num} pages: cooling down {wait:.0f}s ---"
        )
        page.wait_for_timeout(int(wait * 1000))

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scrape(self, url: str, max_pages: int = 5, resume: bool = False) -> list[dict]:
        max_pages = min(max_pages, MAX_PAGES_HARD_LIMIT)

        if resume:
            results, seen_ids, start_page = self._load_checkpoint(url)
        else:
            results, seen_ids, start_page = [], set(), 0
            self.clear_checkpoint()

        if start_page >= max_pages:
            logger.info("Checkpoint shows all pages already scraped.")
            return results

        stealth = Stealth()
        browser = None
        pw_ctx = None
        scrape_start = time.time()

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

            self._load_cookies(context)
            page = context.new_page()

            xhr_pool: list[dict] = []
            xhr_count_at_last_check = 0

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
                            xhr_pool.extend(found)
                            logger.info(f"XHR captured {len(found)} listings from {resp.url[:90]}")
                except Exception:
                    pass

            page.on("response", on_response)

            consecutive_empty = 0
            pages_done_this_session = 0
            block_retries = 0
            MAX_BLOCK_RETRIES = 3

            for p_num in range(start_page + 1, max_pages + 1):
                page_start = time.time()
                pages_done_this_session += 1

                elapsed_total = time.time() - scrape_start
                rate = len(results) / max(pages_done_this_session - 1, 1)
                remaining = max_pages - p_num
                eta_sec = (elapsed_total / max(pages_done_this_session - 1, 1)) * remaining

                logger.info(
                    f"Page {p_num}/{max_pages} | "
                    f"{len(results)} listings | "
                    f"~{rate:.0f}/page | "
                    f"ETA ~{eta_sec/60:.0f}min"
                )

                target_url = self._url_with_page(url, p_num)

                try:
                    page.goto(target_url, wait_until="networkidle", timeout=60_000)
                except Exception as e:
                    logger.warning(f"networkidle timeout on page {p_num}, continuing")
                    try:
                        page.wait_for_timeout(3000)
                    except Exception:
                        logger.error(f"Navigation fully failed on page {p_num}")
                        break

                self._wait_for_xhr(xhr_pool, timeout_sec=6.0)

                base_lo, base_hi = BASE_PAGE_DELAY
                inc_lo, inc_hi = BACKOFF_INCREMENT
                extra = min(p_num - 1, 20) * random.uniform(inc_lo, inc_hi)
                page.wait_for_timeout(int((random.uniform(base_lo, base_hi) + extra) * 1000))

                html = page.content()

                # --- Block / CAPTCHA handling with retries ---
                if self._is_blocked(html):
                    block_retries += 1
                    if block_retries > MAX_BLOCK_RETRIES:
                        logger.error(f"Blocked {block_retries} times. Stopping to protect IP.")
                        break
                    self._wait_for_human(page, context, "Access denied by Akamai WAF.", 120_000)
                    try:
                        page.goto(target_url, wait_until="networkidle", timeout=60_000)
                        page.wait_for_timeout(5000)
                        html = page.content()
                        if self._is_blocked(html):
                            logger.error("Still blocked after retry. Taking a long break...")
                            page.wait_for_timeout(random.randint(120_000, 300_000))
                            continue
                    except Exception:
                        break
                else:
                    block_retries = max(0, block_retries - 1)

                if self._is_captcha(html):
                    self._wait_for_human(page, context, "CAPTCHA detected!", 300_000)
                    html = page.content()
                    if self._is_captcha(html):
                        logger.warning("CAPTCHA still present. Retrying page...")
                        continue

                self._save_cookies(context)
                self._human_behave(page)

                # --- Extraction pipeline ---
                new_xhr = xhr_pool[xhr_count_at_last_check:]
                xhr_count_at_last_check = len(xhr_pool)

                raw_listings: list[dict] = list(new_xhr)

                script_listings = self._extract_from_scripts(page)
                if script_listings:
                    raw_listings.extend(script_listings)

                source = "XHR/script" if raw_listings else "DOM"

                if not raw_listings:
                    raw_listings = self._extract_from_dom(page)

                if not raw_listings:
                    consecutive_empty += 1
                    logger.warning(f"No listings on page {p_num} (empty streak: {consecutive_empty})")
                    try:
                        page.screenshot(path=f"logs/browser_page_{p_num}.png", full_page=True)
                    except Exception:
                        pass
                    self._save_checkpoint(results, seen_ids, p_num, url)
                    if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                        logger.warning(f"{MAX_CONSECUTIVE_EMPTY} consecutive empty pages -- stopping.")
                        break
                    continue

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

                if new_count > 0:
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1

                page_sec = time.time() - page_start
                logger.info(
                    f"Page {p_num}: +{new_count} new ({len(results)} total) "
                    f"[{source}] ({page_sec:.1f}s)"
                )

                self._save_checkpoint(results, seen_ids, p_num, url)

                if self._on_page_done:
                    try:
                        self._on_page_done(results, seen_ids, p_num)
                    except Exception as e:
                        logger.debug(f"Page callback error: {e}")

                if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                    logger.info(f"{MAX_CONSECUTIVE_EMPTY} consecutive empty/duplicate pages -- end of results.")
                    break

                self._batch_break(page, p_num)

            elapsed = time.time() - scrape_start
            logger.info(
                f"Scraper finished: {len(results)} unique listings in "
                f"{elapsed/60:.1f}min ({pages_done_this_session} pages)"
            )
            return results

        except KeyboardInterrupt:
            logger.info(f"Interrupted! {len(results)} listings already in checkpoint.")
            return results

        except Exception as e:
            logger.error(f"Scraper crashed: {e}", exc_info=True)
            return results

        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if pw_ctx:
                    pw_ctx.__exit__(None, None, None)
            except Exception:
                pass
