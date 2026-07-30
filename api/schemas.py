from pydantic import BaseModel
from typing import List, Optional

class NearMiss(BaseModel):
    miss_id: str
    score: float

class MatchedRoom(BaseModel):
    hotel_a_id: str
    hotel_b_id: str
    room_a_id: str
    room_b_id: str
    score: float

class CanonicalHotelSummary(BaseModel):
    id: str
    name: Optional[str]
    address: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    stars: Optional[str]
    confidence: Optional[float]

class CanonicalHotelDetail(CanonicalHotelSummary):
    b_lat: Optional[float]
    b_lon: Optional[float]
    amenities: List[str]
    image_urls: List[str]
    source_a_id: Optional[str]
    source_b_id: Optional[str]
    near_misses: List[NearMiss]
    matched_rooms: List[MatchedRoom]

class PaginatedHotels(BaseModel):
    items: List[CanonicalHotelSummary]
    total: int
    page: int
    size: int
