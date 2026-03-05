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


class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    payment: Optional[str] = None
    contacts: Optional[str] = None


class ListingResponse(ListingBase):
    id: int
    user_id: int
    status: str
    created_at: datetime
    username: Optional[str] = None

    class Config:
        from_attributes = True


class TermsDocumentResponse(BaseModel):
    version: str
    title: str
    content: str
    created_at: Optional[datetime] = None


class ComplianceResponse(BaseModel):
    user_id: int
    telegram_id: int
    username: Optional[str] = None
    role: str
    is_banned: bool
    ban_reason: Optional[str] = None
    accepted_terms_version: Optional[str] = None
    accepted_terms_at: Optional[datetime] = None
    active_terms_version: Optional[str] = None
    is_terms_accepted: bool


class AcceptTermsRequest(BaseModel):
    version: str


class AdminUserRoleUpdateRequest(BaseModel):
    role: str


class AdminUserBanRequest(BaseModel):
    reason: Optional[str] = None


class DeleteListingRequest(BaseModel):
    reason: str


class AdminListingCloseRequest(BaseModel):
    reason: str


class AdminUserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    role: str
    is_banned: bool
    ban_reason: Optional[str] = None
    accepted_terms_version: Optional[str] = None
    accepted_terms_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AdminAuditResponse(BaseModel):
    id: int
    admin_user_id: int
    target_user_id: Optional[int] = None
    action: str
    details: Optional[str] = None
    created_at: Optional[datetime] = None


class AdminListingResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    type: str
    title: str
    description: str
    address: str
    payment: str
    contacts: str
    status: str
    created_at: Optional[datetime] = None

