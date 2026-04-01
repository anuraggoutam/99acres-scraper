from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class ScraperConfig(BaseSettings):
    base_url: str = "https://www.99acres.com/api-aggregator/srp/search"
    search_url: str = "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R"

    city: int = 7
    preference: str = "S"
    res_com: str = "R"
    area_unit: int = 1
    page_size: int = 25

    bedroom_num: Optional[int] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None

    max_pages: int = 50
    delay_min: float = 3.0
    delay_max: float = 6.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

config = ScraperConfig()