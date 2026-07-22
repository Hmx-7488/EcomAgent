"""Asset and image generation task models."""

import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class Asset(Base):
    """Uploaded source images and generated assets."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # source, generated
    source_type: Mapped[Optional[str]] = mapped_column(
        String(32)
    )  # upload, generation
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class ImageGenerationTask(Base):
    """Async image generation task tracker."""

    __tablename__ = "image_generation_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    source_asset_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("assets.id")
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, processing, completed, failed
    style: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(128))
    prompt: Mapped[Optional[str]] = mapped_column(Text)
    result_asset_ids: Mapped[Optional[str]] = mapped_column(
        Text
    )  # JSON array of generated asset IDs
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )