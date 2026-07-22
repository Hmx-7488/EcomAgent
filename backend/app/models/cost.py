import datetime
from typing import Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base
class SKUCost(Base):
    __tablename__ = "sku_costs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), unique=True, nullable=False)
    purchase_cost: Mapped[Optional[float]] = mapped_column(Float)
    packaging_cost: Mapped[Optional[float]] = mapped_column(Float)
    shipping_subsidy: Mapped[Optional[float]] = mapped_column(Float)
    platform_fee: Mapped[Optional[float]] = mapped_column(Float)
    marketing_allocation: Mapped[Optional[float]] = mapped_column(Float)
    after_sales_loss: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
