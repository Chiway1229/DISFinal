from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    initial_stock = Column(Integer, nullable=False)
    current_stock = Column(Integer, nullable=False)
    reserve_price = Column(Float, nullable=False)  # 底價
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, stock={self.current_stock}/{self.initial_stock})>"
