import random
import time
from fake_useragent import UserAgent
from httpx import HTTPTransport

ua = UserAgent()

def get_random_headers(referer: str) -> dict:
    return {
        "User-Agent": ua.random,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "Origin": "https://www.99acres.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
    }

def random_delay(min_sec: float = 2.0, max_sec: float = 5.0):
    time.sleep(random.uniform(min_sec, max_sec))

def normalize_price(price_str: str) -> float | None:
    try:
        price_str = price_str.replace("₹", "").replace(",", "").strip().lower()
        if "cr" in price_str:
            return float(price_str.replace("cr", "")) * 10000000
        if "lac" in price_str:
            return float(price_str.replace("lac", "")) * 100000
        return float(price_str)
    except:
        return None

def normalize_area(area_str: str) -> int | None:
    try:
        return int("".join(filter(str.isdigit, area_str)))
    except:
        return None