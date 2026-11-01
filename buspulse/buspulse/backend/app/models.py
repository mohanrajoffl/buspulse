from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GpsUpdateIn(BaseModel):
    bus_id: str = Field(min_length=1, max_length=20)
    latitude: float
    longitude: float
    timestamp: datetime
    speed_kmh: Optional[float] = Field(default=None, ge=0, le=200)


class RouteIn(BaseModel):
    route_name: str = Field(min_length=1, max_length=80)
    start_point: str = Field(min_length=1, max_length=80)
    end_point: str = Field(min_length=1, max_length=80)


class StopIn(BaseModel):
    stop_name: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    sequence_number: int = Field(ge=1)
    scheduled_offset_min: Optional[float] = Field(default=None, ge=0)


class BusIn(BaseModel):
    bus_id: str = Field(min_length=1, max_length=20)
    registration: Optional[str] = Field(default=None, max_length=20)
    route_id: int
