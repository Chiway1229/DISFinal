from sqlalchemy import Column, Integer, Float, DateTime, String, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    alpha = Column(Float, nullable=False)  # 價格權重 α
    beta = Column(Float, nullable=False)   # 時間權重 β
    gamma = Column(Float, nullable=False)  # 會員權重 γ
    inventory_limit = Column(Integer, nullable=False)  # K: 最多得標人數
    status = Column(String, default="pending")  # pending, active, completed
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Sale(id={self.id}, product_id={self.product_id}, status={self.status}, K={self.inventory_limit})>"
