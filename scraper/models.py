from pydantic import BaseModel, Field
from typing import Optional

class Property(BaseModel):
    prop_id: str
    title: str
    price: str = Field(..., description="Raw price string e.g. ₹1.25 Cr")
    price_numeric: Optional[float] = None
    location: str
    bhk: Optional[str] = None
    area_sqft: Optional[int] = None
    builder: Optional[str] = None
    listing_url: str
    contact: Optional[str] = None
    metadata: dict = Field(default_factory=dict)