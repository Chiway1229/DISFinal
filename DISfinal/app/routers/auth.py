"""
認證路由 - 註冊、登入
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.user import User
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from app.services.auth_service import hash_password, verify_password, create_access_token
import random

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    註冊新用戶

    - 檢查 email 是否已存在
    - 隨機分配 weight (0.5-1.0)
    - 密碼雜湊後儲存
    - 處理高並發下的 unique constraint violation
    """
    # 隨機分配會員權重 W (0.5-1.0)
    weight = random.uniform(0.5, 1.0)

    # 建立新用戶
    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        weight=weight
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError:
        # 捕獲資料庫 unique constraint violation (高並發下的 race condition)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    用戶登入

    - 驗證 email 和密碼
    - 產生 JWT token
    - 返回 token 和用戶資訊
    """
    # 查詢用戶
    user = db.query(User).filter(User.email == credentials.email).first()

    # 驗證用戶和密碼
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 產生 JWT token
    token = create_access_token(
        data={
            "user_id": user.id,
            "email": user.email,
            "weight": user.weight
        }
    )

    return TokenResponse(
        access_token=token,
        user_id=user.id,
        weight=user.weight
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    token: str,
    db: Session = Depends(get_db)
):
    """
    取得當前用戶資訊 (需要 token)
    """
    from app.services.auth_service import decode_access_token
    from jose import JWTError

    try:
        payload = decode_access_token(token)
        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
