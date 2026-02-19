from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ListingBase(BaseModel):
    type: str  # 'task' или 'worker'
    title: str
    description: str
    address: str
    payment: str
    contacts: str
    latitude: float
    longitude: float


class ListingCreate(ListingBase):
    pass


class ListingResponse(ListingBase):
    id: int
    user_id: int
    status: str
    created_at: datetime
    username: Optional[str] = None

    class Config:
        from_attributes = True

