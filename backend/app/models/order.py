"""Order and after-sales models (P0-extended readiness)."""

import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    buyer_name: Mapped[Optional[str]] = mapped_column(String(128))
    buyer_phone: Mapped[Optional[str]] = mapped_column(String(32))
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, paid, refunded
    shipment_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, shipped, delivered, signed
    logistics_company: Mapped[Optional[str]] = mapped_column(String(128))
    logistics_tracking_no: Mapped[Optional[str]] = mapped_column(String(128))
    shipping_address: Mapped[Optional[str]] = mapped_column(Text)
    signed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_order_id", "order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"))
    sku_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("skus.id"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")


class AfterSalesRule(Base):
    __tablename__ = "after_sales_rules"
    __table_args__ = (Index("ix_after_sales_rules_product_id", "product_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    category: Mapped[Optional[str]] = mapped_column(String(128))
    support_7_days: Mapped[bool] = mapped_column(default=True)
    after_sales_days: Mapped[int] = mapped_column(Integer, default=7)
    require_evidence: Mapped[bool] = mapped_column(default=False)
    allow_refund: Mapped[bool] = mapped_column(default=True)
    allow_return: Mapped[bool] = mapped_column(default=True)
    allow_exchange: Mapped[bool] = mapped_column(default=True)
    allow_resend: Mapped[bool] = mapped_column(default=False)
    rule_text: Mapped[Optional[str]] = mapped_column(Text)
