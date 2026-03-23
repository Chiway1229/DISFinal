"""
管理員路由 - 商品管理、活動管理
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.product import Product
from app.models.sale import Sale
from app.schemas import ProductCreate, ProductResponse, SaleCreate, SaleResponse
from app.services.redis_service import get_redis_service, RedisService
from app.models.bid import Bid
from typing import List

router = APIRouter(prefix="/admin", tags=["admin"])


# ===== 商品管理 =====

@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(product_data: ProductCreate, db: Session = Depends(get_db)):
    """
    建立新商品

    - name: 商品名稱
    - description: 商品描述 (選填)
    - initial_stock: 初始庫存
    - reserve_price: 底價
    """
    product = Product(
        name=product_data.name,
        description=product_data.description,
        initial_stock=product_data.initial_stock,
        current_stock=product_data.initial_stock,  # 初始時 current = initial
        reserve_price=product_data.reserve_price
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


@router.get("/products", response_model=List[ProductResponse])
async def list_products(db: Session = Depends(get_db)):
    """列出所有商品"""
    products = db.query(Product).all()
    return products


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """取得單一商品"""
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return product


# ===== 活動管理 =====

@router.post("/sales", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(sale_data: SaleCreate, db: Session = Depends(get_db)):
    """
    建立新搶購活動

    - product_id: 商品 ID
    - start_time: 開始時間
    - end_time: 結束時間
    - alpha, beta, gamma: 評分公式權重
    - inventory_limit (K): 最多得標人數
    """
    # 檢查商品是否存在
    product = db.query(Product).filter(Product.id == sale_data.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # 檢查庫存是否足夠
    if sale_data.inventory_limit > product.current_stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inventory limit ({sale_data.inventory_limit}) exceeds current stock ({product.current_stock})"
        )

    # 建立活動
    sale = Sale(
        product_id=sale_data.product_id,
        start_time=sale_data.start_time,
        end_time=sale_data.end_time,
        alpha=sale_data.alpha,
        beta=sale_data.beta,
        gamma=sale_data.gamma,
        inventory_limit=sale_data.inventory_limit,
        status="pending"  # 預設為 pending
    )

    db.add(sale)
    db.commit()
    db.refresh(sale)

    # 初始化 Redis (稍後實作)
    # await init_sale_in_redis(sale.id, sale_data)

    return sale


@router.get("/sales")
async def list_sales(db: Session = Depends(get_db)):
    """列出所有活動 (包含商品名稱)"""
    sales = db.query(Sale).order_by(Sale.start_time.desc()).all()

    # 加入商品名稱
    result = []
    for sale in sales:
        product = db.query(Product).filter(Product.id == sale.product_id).first()
        sale_dict = {
            "id": sale.id,
            "product_id": sale.product_id,
            "product_name": product.name if product else "未知商品",
            "start_time": sale.start_time.isoformat(),
            "end_time": sale.end_time.isoformat(),
            "alpha": sale.alpha,
            "beta": sale.beta,
            "gamma": sale.gamma,
            "inventory_limit": sale.inventory_limit,
            "status": sale.status,
            "created_at": sale.created_at.isoformat()
        }
        result.append(sale_dict)

    return result


@router.get("/sales/{sale_id}", response_model=SaleResponse)
async def get_sale(sale_id: int, db: Session = Depends(get_db)):
    """取得單一活動"""
    sale = db.query(Sale).filter(Sale.id == sale_id).first()

    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    return sale


@router.patch("/sales/{sale_id}/start")
async def start_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    redis_service: RedisService = Depends(get_redis_service)
):
    """
    啟動活動

    - 將狀態從 pending 改為 active
    - 初始化 Redis 排行榜和參數快取
    """
    sale = db.query(Sale).filter(Sale.id == sale_id).first()

    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    if sale.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sale is already {sale.status}"
        )

    # 更新狀態
    sale.status = "active"
    db.commit()

    # 初始化 Redis 參數快取
    start_time_ms = int(sale.start_time.timestamp() * 1000)
    redis_service.init_sale_params(
        sale_id=sale_id,
        alpha=sale.alpha,
        beta=sale.beta,
        gamma=sale.gamma,
        start_time_ms=start_time_ms,
        inventory_limit=sale.inventory_limit
    )

    # 清空排行榜 (防止之前的測試數據)
    redis_service.clear_leaderboard(sale_id)

    return {
        "message": "Sale started",
        "sale_id": sale_id,
        "status": sale.status,
        "start_time_ms": start_time_ms
    }


@router.patch("/sales/{sale_id}/end")
async def end_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    redis_service: RedisService = Depends(get_redis_service)
):
    """
    結束活動

    - 將狀態從 active 改為 completed
    - 確定前 K 名得標者
    - 扣減商品庫存
    - 驗證無超賣
    """
    sale = db.query(Sale).filter(Sale.id == sale_id).first()

    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    if sale.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sale is not active (current status: {sale.status})"
        )

    # 取得前 K 名得標者 (直接返回 list)
    winners = redis_service.get_leaderboard(
        sale_id=sale_id,
        limit=sale.inventory_limit
    )
    winners_count = len(winners)

    # 取得商品
    product = db.query(Product).filter(Product.id == sale.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # 驗證庫存是否足夠
    if product.current_stock < winners_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock: have {product.current_stock}, need {winners_count}"
        )

    # 扣減庫存
    product.current_stock -= winners_count

    # 更新活動狀態
    sale.status = "completed"

    # 標記得標者 (在資料庫中更新 bid 記錄)
    winner_user_ids = [winner["user_id"] for winner in winners]
    db.query(Bid).filter(
        Bid.sale_id == sale_id,
        Bid.user_id.in_(winner_user_ids)
    ).update({"is_winner": True}, synchronize_session=False)

    db.commit()

    return {
        "message": "Sale ended successfully",
        "sale_id": sale_id,
        "status": sale.status,
        "winners_count": winners_count,
        "remaining_stock": product.current_stock,
        "winners": winners[:5]  # 只返回前 5 名
    }


@router.delete("/sales/{sale_id}")
async def delete_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    redis_service: RedisService = Depends(get_redis_service)
):
    """
    刪除活動

    - 刪除 Redis 排行榜數據
    - 刪除相關的出價記錄 (bids)
    - 刪除資料庫中的活動記錄
    """
    sale = db.query(Sale).filter(Sale.id == sale_id).first()

    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    # 先刪除相關的出價記錄（避免外鍵約束錯誤）
    deleted_bids = db.query(Bid).filter(Bid.sale_id == sale_id).delete()

    # 清除 Redis 數據
    redis_service.clear_leaderboard(sale_id)

    # 刪除資料庫記錄
    db.delete(sale)
    db.commit()

    return {
        "message": "Sale deleted successfully",
        "sale_id": sale_id,
        "deleted_bids": deleted_bids
    }
