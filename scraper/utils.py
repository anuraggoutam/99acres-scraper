import json
import re
from datetime import datetime, timezone


def normalize_price(price_str) -> float | None:
    if not price_str:
        return None
    try:
        if isinstance(price_str, (int, float)):
            return float(price_str)
        cleaned = str(price_str).replace("₹", "").replace(",", "").replace(" ", "").strip().lower()
        num_match = re.search(r"[\d.]+", cleaned)
        if not num_match:
            return None
        num = float(num_match.group())
        if "cr" in cleaned or "crore" in cleaned:
            return num * 10_000_000
        if "lac" in cleaned or "lakh" in cleaned or "lacs" in cleaned:
            return num * 100_000
        if cleaned.endswith("l"):
            return num * 100_000
        if cleaned.endswith("k"):
            return num * 1_000
        return num
    except Exception:
        return None


def epoch_to_date(val) -> str | None:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            ts = val / 1000 if val > 1e12 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        s = str(val).strip()
        return s if s and len(s) > 4 else None
    except Exception:
        return str(val) if val else None


_FACING_MAP = {
    "1": "East", "2": "West", "3": "North", "4": "South",
    "5": "North-East", "6": "North-West", "7": "South-East", "8": "South-West",
}


def facing_map(code: str) -> str | None:
    return _FACING_MAP.get(str(code).strip(), code if code else None)


_AVAILABILITY_MAP = {
    "I": "Ready to Move",
    "U": "Under Construction",
    "Q": "Under Construction",
    "N": "New Launch",
}


def availability_map(code: str) -> str | None:
    return _AVAILABILITY_MAP.get(str(code).strip(), code if code else None)


_FURNISH_MAP = {
    "1": "Furnished",
    "2": "Furnished",
    "3": "Unfurnished",
    "4": "Semifurnished",
}


def furnish_map(code: str) -> str | None:
    return _FURNISH_MAP.get(str(code).strip(), code if code else None)


_AGE_MAP = {
    "1": "1-5 years",
    "2": "5-10 years",
    "3": "10+ years",
    "4": "New Construction",
}


def age_map(code: str) -> str | None:
    return _AGE_MAP.get(str(code).strip(), f"{code} years" if code and code.isdigit() else code)


_OVERLOOKING_MAP = {
    "1": "Main Road",
    "2": "Garden/Park",
    "3": "Pool",
    "4": "Other",
}


def parse_overlooking(raw: str) -> str | None:
    if not raw:
        return None
    codes = str(raw).split(",")
    labels = [_OVERLOOKING_MAP.get(c.strip(), c.strip()) for c in codes if c.strip()]
    return ", ".join(labels) if labels else None


def parse_parking(raw) -> str | None:
    if not raw:
        return None
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            parts = []
            if raw.get("O"):
                parts.append(f"Open: {raw['O']}")
            if raw.get("C"):
                parts.append(f"Covered: {raw['C']}")
            return ", ".join(parts) if parts else None
    except Exception:
        return str(raw)
