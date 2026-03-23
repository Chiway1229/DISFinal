"""
出價路由 - 核心競標功能 (優化版)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from datetime import datetime
from jose import JWTError
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.database import get_db, SessionLocal
from app.models.sale import Sale
from app.models.product import Product
from app.models.bid import Bid
from app.schemas import BidCreate, BidResponse, LeaderboardResponse, LeaderboardEntry
from app.services.auth_service import decode_access_token
from app.services.score_calculator import calculate_score
from app.services.redis_service import get_redis_service, RedisService

router = APIRouter(prefix="/bids", tags=["bids"])

# 背景執行緒池 (避免為每個出價創建新執行緒)
_executor = ThreadPoolExecutor(max_workers=10)

# 活動快取 (避免重複查詢資料庫)
_sale_cache = {}
_product_cache = {}


def save_bid_sync(user_id, product_id, sale_id, price, response_time_ms, score, rank, is_winner):
    """同步背景儲存出價到資料庫"""
    db = SessionLocal()
    try:
        bid = Bid(
            user_id=user_id,
            product_id=product_id,
            sale_id=sale_id,
            price=price,
            response_time_ms=response_time_ms,
            calculated_score=score,
            rank=rank,
            is_winner=is_winner
        )
        db.add(bid)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def get_current_user_from_token(authorization: str = Header(...)):
    """
    從 Authorization header 取得當前用戶資訊

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        {"user_id": int, "email": str, "weight": float}

    Raises:
        HTTPException: token 無效或過期
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "")

    try:
        payload = decode_access_token(token)
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_cached_sale(db: Session, sale_id: int, redis_service: RedisService):
    """從 Redis 快取或資料庫取得活動資訊"""
    cache_key = f"sale_cache:{sale_id}"

    # 先從 Redis 快取讀取
    cached = redis_service.redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 從資料庫讀取
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if sale:
        sale_data = {
            "id": sale.id,
            "product_id": sale.product_id,
            "status": sale.status,
            "start_time_ms": int(sale.start_time.timestamp() * 1000),
            "alpha": sale.alpha,
            "beta": sale.beta,
            "gamma": sale.gamma,
            "inventory_limit": sale.inventory_limit
        }
        # 快取 60 秒
        redis_service.redis.setex(cache_key, 60, json.dumps(sale_data))
        return sale_data
    return None


def get_cached_product(db: Session, product_id: int, redis_service: RedisService):
    """從 Redis 快取或資料庫取得商品資訊"""
    cache_key = f"product_cache:{product_id}"

    # 先從 Redis 快取讀取
    cached = redis_service.redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 從資料庫讀取
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product_data = {
            "id": product.id,
            "reserve_price": float(product.reserve_price)
        }
        # 快取 300 秒 (商品資訊變動少)
        redis_service.redis.setex(cache_key, 300, json.dumps(product_data))
        return product_data
    return None


@router.post("", response_model=BidResponse)
async def submit_bid(
    bid_data: BidCreate,
    current_user: dict = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
    redis_service: RedisService = Depends(get_redis_service)
):
    """
    提交出價 - 核心功能! (優化版 - 使用 Redis 快取減少 DB 查詢)

    流程:
    1. 驗證 JWT token 取得 user_id 和 weight
    2. 從 Redis 快取檢查活動狀態 (必須是 active)
    3. 從 Redis 快取檢查價格是否 >= 底價
    4. 計算反應時間 T (毫秒)
    5. 計算 Score = α·P + β/(T+1) + γ·W
    6. 原子性更新 Redis 排行榜 (Lua 腳本)
    7. 非同步儲存到資料庫 (不阻塞回應)
    8. 返回結果 (score, rank, is_winner)
    """
    sale_id = bid_data.sale_id
    price = bid_data.price
    user_id = current_user["user_id"]
    weight = current_user["weight"]

    # 1. 從快取檢查活動是否存在且為 active
    sale_data = get_cached_sale(db, sale_id, redis_service)

    if not sale_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    if sale_data["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sale is not active (current status: {sale_data['status']})"
        )

    # 2. 從快取檢查價格是否 >= 底價
    product_data = get_cached_product(db, sale_data["product_id"], redis_service)

    if price < product_data["reserve_price"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Price must be >= {product_data['reserve_price']} (reserve price)"
        )

    # 3. 計算反應時間 T (毫秒)
    current_time_ms = int(datetime.now().timestamp() * 1000)
    response_time_ms = current_time_ms - sale_data["start_time_ms"]

    # 防止負數 (如果系統時間有問題)
    if response_time_ms < 0:
        response_time_ms = 0

    # 4. 計算 Score
    score = calculate_score(
        price=price,
        response_time_ms=response_time_ms,
        weight=weight,
        alpha=sale_data["alpha"],
        beta=sale_data["beta"],
        gamma=sale_data["gamma"]
    )

    # 5. 原子性更新 Redis 排行榜 (Lua 腳本保證原子性)
    is_winner, rank = redis_service.update_leaderboard(
        sale_id=sale_id,
        user_id=user_id,
        score=score,
        max_winners=sale_data["inventory_limit"]
    )

    # 6. 背景儲存到資料庫 (不阻塞回應，Redis 已經是真相來源)
    _executor.submit(
        save_bid_sync,
        user_id, sale_data["product_id"], sale_id, price,
        response_time_ms, score, rank + 1, is_winner
    )

    # 7. 觸發 WebSocket 廣播更新排行榜 (非同步，不等待)
    try:
        from app.routers.websocket import broadcast_leaderboard_update
        asyncio.create_task(broadcast_leaderboard_update(sale_id))
    except Exception:
        pass  # WebSocket 廣播失敗不影響出價結果

    # 8. 返回結果
    return BidResponse(
        message="Bid submitted successfully (current status, may change)",
        score=score,
        rank=rank + 1,
        is_winner=is_winner,
        response_time_ms=response_time_ms
    )


@router.get("/{sale_id}/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    sale_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    redis_service: RedisService = Depends(get_redis_service)
):
    """
    取得排行榜前 N 名

    Args:
        sale_id: 活動 ID
        limit: 返回前幾名 (預設 10)

    Returns:
        LeaderboardResponse: 排行榜列表
    """
    # 檢查活動是否存在
    sale = db.query(Sale).filter(Sale.id == sale_id).first()

    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    # 從 Redis 取得排行榜
    leaderboard_data = redis_service.get_leaderboard(sale_id, limit)

    # 轉換為 Pydantic 模型
    leaderboard = [
        LeaderboardEntry(
            rank=entry["rank"],
            user_id=entry["user_id"],
            score=entry["score"]
        )
        for entry in leaderboard_data
    ]

    return LeaderboardResponse(
        sale_id=sale_id,
        leaderboard=leaderboard
    )
