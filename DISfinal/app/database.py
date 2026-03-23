from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# 創建資料庫引擎 - 優化連接池配置以支援高並發
# PostgreSQL max_connections=1000，每個 Pod 最多使用 5+10=15 連接
# 最多 30 個 Pod，總計最多 450，預留給其他連接
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # 測試連接是否有效
    pool_size=5,             # 每 Pod 基礎連接數 (減少以避免連線耗盡)
    max_overflow=10,         # 溢出連接數
    pool_timeout=10,         # 縮短等待超時時間 (快速失敗重試)
    pool_recycle=300,        # 5 分鐘回收連接，避免連接過期
    echo=False               # 關閉 SQL 日誌以提升效能
)

# 創建 Session 工廠
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 創建基礎類
Base = declarative_base()


# 依賴注入函數
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
