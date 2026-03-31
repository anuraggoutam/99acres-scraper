from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

class ScraperConfig(BaseSettings):
    base_url: str = "https://www.99acres.com/api-aggregator/srp/search"
    search_url: str = "https://www.99acres.com/search/property/buy/noida?city=7&property_type=91&preference=S&area_unit=1&res_com=C"
    
    # Search filters (easily extendable via CLI)
    city: int = 7
    property_type: int = 91
    preference: str = "S"
    res_com: str = "C"
    area_unit: int = 1
    page_size: int = 30
    
    # Optional extra filters
    bedroom_num: Optional[int] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    
    max_pages: int = 50          # safety
    delay_min: float = 2.0
    delay_max: float = 5.0
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

config = ScraperConfig()