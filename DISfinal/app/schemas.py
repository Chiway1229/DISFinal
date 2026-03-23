"""
Pydantic Schemas for request/response validation
"""
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


# ===== User Schemas =====
class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    weight: float
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    weight: float


# ===== Product Schemas =====
class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    initial_stock: int
    reserve_price: float


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    initial_stock: int
    current_stock: int
    reserve_price: float
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Sale Schemas =====
class SaleCreate(BaseModel):
    product_id: int
    start_time: datetime
    end_time: datetime
    alpha: float  # 價格權重
    beta: float   # 時間權重
    gamma: float  # 會員權重
    inventory_limit: int  # K: 最多得標人數


class SaleResponse(BaseModel):
    id: int
    product_id: int
    start_time: datetime
    end_time: datetime
    alpha: float
    beta: float
    gamma: float
    inventory_limit: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Bid Schemas =====
class BidCreate(BaseModel):
    sale_id: int
    price: float


class BidResponse(BaseModel):
    message: str
    score: float
    rank: int
    is_winner: bool
    response_time_ms: int


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    score: float


class LeaderboardResponse(BaseModel):
    sale_id: int
    leaderboard: list[LeaderboardEntry]
