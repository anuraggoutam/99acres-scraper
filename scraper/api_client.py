import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .config import config
from .utils import get_random_headers, random_delay
import logging

logger = logging.getLogger(__name__)

class ApiClient:
    def __init__(self, proxy: str | None = None):
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        transport = httpx.HTTPTransport(retries=2)
        
        self.client = httpx.Client(
            timeout=30.0,
            limits=limits,
            transport=transport,
            proxy=proxy,
            follow_redirects=True,
        )
        self.headers_base = None

    def _build_params(self, page: int) -> dict:
        params = {
            "city": config.city,
            "property_type": config.property_type,
            "preference": config.preference,
            "res_com": config.res_com,
            "area_unit": config.area_unit,
            "page": page,
            "page_size": config.page_size,
            "platform": "DESKTOP",
            "moduleName": "GRAILS_SRP",
            "workflow": "GRAILS_SRP",
            "seoUrlType": "DEFAULT",
        }
        if config.bedroom_num:
            params["bedroom_num"] = config.bedroom_num
        if config.budget_min:
            params["budget_min"] = config.budget_min
        if config.budget_max:
            params["budget_max"] = config.budget_max
        return params

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        reraise=True,
    )
    def get_listings(self, page: int) -> dict:
        url = config.base_url
        params = self._build_params(page)
        headers = get_random_headers(config.search_url)
        
        logger.info(f"Fetching page {page} via API")
        resp = self.client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        
        data = resp.json()
        
        # Robust key detection (site sometimes changes wrapper)
        listings = (
            data.get("properties")
            or data.get("srpResults")
            or data.get("data")
            or data.get("listings")
            or data.get("newProjects")
            or []
        )
        
        if not isinstance(listings, list):
            listings = []
            
        logger.info(f"Page {page}: {len(listings)} listings")
        random_delay(config.delay_min, config.delay_max)
        
        return {
            "listings": listings,
            "total": data.get("totalCount") or data.get("total") or len(listings),
            "has_more": bool(data.get("pageInfo", {}).get("hasNext") or len(listings) == config.page_size),
        }