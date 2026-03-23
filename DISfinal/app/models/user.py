from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    weight = Column(Float, default=0.5)  # W: 會員權重 (0.5-1.0)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, weight={self.weight})>"
