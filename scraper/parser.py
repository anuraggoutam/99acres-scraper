from .models import Property
from .utils import normalize_price, normalize_area
import logging

logger = logging.getLogger(__name__)

def parse_property(raw: dict) -> Property | None:
    try:
        prop_url = raw.get("propUrl") or raw.get("url") or ""
        if prop_url and not prop_url.startswith("http"):
            prop_url = "https://www.99acres.com" + prop_url

        return Property(
            prop_id=str(raw.get("propId") or raw.get("id") or ""),
            title=raw.get("title") or raw.get("projectName") or "",
            price=raw.get("price") or raw.get("displayPrice") or "",
            price_numeric=normalize_price(raw.get("price") or ""),
            location=raw.get("locality") or raw.get("address") or "",
            bhk=raw.get("bedroom") or raw.get("bhk") or raw.get("propTypeStr"),
            area_sqft=normalize_area(raw.get("superArea") or raw.get("area") or ""),
            builder=raw.get("builderName") or raw.get("projectName") or raw.get("ownerName"),
            listing_url=prop_url,
            contact=raw.get("contactPerson") or raw.get("phone") or "",
            metadata=raw,
        )
    except Exception as e:
        logger.warning(f"Failed to parse property: {e}")
        return None