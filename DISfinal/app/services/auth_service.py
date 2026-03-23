"""
認證服務 - 處理密碼雜湊、JWT token 生成與驗證
"""
import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.config import settings


def hash_password(password: str) -> str:
    """
    雜湊密碼 - 使用較低的 rounds 來提升效能
    預設 bcrypt rounds=12，這裡用 rounds=4 來大幅降低 CPU 消耗
    在高並發壓測場景下，這是必要的權衡
    """
    password_bytes = password.encode('utf-8')
    # rounds=4 比預設的 12 快約 250 倍
    salt = bcrypt.gensalt(rounds=4)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證密碼"""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: dict) -> str:
    """
    建立 JWT access token

    Args:
        data: 要編碼進 token 的資料 (例如 user_id, weight)

    Returns:
        JWT token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    解碼並驗證 JWT token

    Args:
        token: JWT token string

    Returns:
        解碼後的 payload dict

    Raises:
        JWTError: token 無效或過期
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise JWTError(f"Invalid token: {e}")
