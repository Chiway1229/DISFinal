from sqlalchemy import Column, Integer, Float, Boolean, DateTime, String, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    response_time_ms = Column(Integer, nullable=False)  # T: 反應時間(毫秒)
    calculated_score = Column(Float)  # 計算出的 Score
    rank = Column(Integer)  # 排名
    is_winner = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_sale_score', 'sale_id', 'calculated_score'),
        Index('idx_user_sale', 'user_id', 'sale_id'),
    )

    def __repr__(self):
        return f"<Bid(id={self.id}, user={self.user_id}, sale={self.sale_id}, score={self.calculated_score}, rank={self.rank})>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    final_price = Column(Float)
    final_score = Column(Float)
    final_rank = Column(Integer)
    status = Column(String, default="completed")
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Transaction(id={self.id}, user={self.user_id}, sale={self.sale_id}, status={self.status})>"
