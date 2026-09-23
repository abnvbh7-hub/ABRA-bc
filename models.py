from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel

class LoginModel(BaseModel):
    username: str
    password:str


class AbraModel(BaseModel):
    timestamp: Optional[datetime] = None
    day: Optional[date] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    speed: Optional[float] = None
    direction: Optional[float] = None

    accel_x: Optional[float] = None
    accel_y: Optional[float] = None
    accel_z: Optional[float] = None

    gyro_x: Optional[float] = None
    gyro_y: Optional[float] = None
    gyro_z: Optional[float] = None

    wifi_count: Optional[int] = None

    vendor: Optional[str] = None
    amount: Optional[float] = None

    battery_level: Optional[float] = None
    is_charging: Optional[bool] = None
    network_type: Optional[str] = None