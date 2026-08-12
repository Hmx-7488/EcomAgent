"""Pydantic schemas for product CRUD."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- SKU & Inventory ---

class InventoryCreate(BaseModel):
    stock_quantity: int = Field(ge=0, default=0)
    locked_quantity: int = Field(ge=0, default=0)
    safety_stock: int = Field(ge=0, default=0)


class InventoryRead(BaseModel):
    id: int
    sku_id: int
    stock_quantity: int
    locked_quantity: int
    safety_stock: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class SKUCreate(BaseModel):
    sku_name: str = Field(min_length=1, max_length=255)
    color: Optional[str] = Field(None, max_length=64)
    size: Optional[str] = Field(None, max_length=64)
    spec: Optional[str] = Field(None, max_length=128)
    price: float = Field(ge=0, allow_inf_nan=False)
    image_url: Optional[str] = Field(None, max_length=512)
    inventory: Optional[InventoryCreate] = None


class SKURead(BaseModel):
    id: int
    product_id: int
    sku_name: str
    color: Optional[str]
    size: Optional[str]
    spec: Optional[str]
    price: float
    image_url: Optional[str]
    status: str
    inventory: Optional[InventoryRead] = None

    model_config = {"from_attributes": True}


class SKUUpdate(BaseModel):
    sku_name: Optional[str] = Field(None, min_length=1, max_length=255)
    color: Optional[str] = Field(None, max_length=64)
    size: Optional[str] = Field(None, max_length=64)
    spec: Optional[str] = Field(None, max_length=128)
    price: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    image_url: Optional[str] = Field(None, max_length=512)
    status: Optional[str] = None


# --- Product ---

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    brand: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    selling_points: Optional[str] = None
    parameters_json: Optional[str] = None
    shipping_rule_text: Optional[str] = None  # P0: free text; P1: structured table
    skus: list[SKUCreate] = Field(default_factory=list)


class ProductRead(BaseModel):
    id: int
    name: str
    category: str
    brand: Optional[str]
    description: Optional[str]
    selling_points: Optional[str]
    parameters_json: Optional[str]
    shipping_rule_text: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    skus: list[SKURead] = []

    model_config = {"from_attributes": True}


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, min_length=1, max_length=128)
    brand: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    selling_points: Optional[str] = None
    parameters_json: Optional[str] = None
    shipping_rule_text: Optional[str] = None
    status: Optional[str] = None


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int


class ProductCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ProductCategoryRead(BaseModel):
    id: int
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class ProductCategoryListResponse(BaseModel):
    items: list[ProductCategoryRead]
    total: int


class CustomerServiceSKURead(BaseModel):
    """Approved customer-service facts; excludes price and inventory."""
    id: int
    product_id: int
    sku_name: str
    color: Optional[str]
    size: Optional[str]
    spec: Optional[str]
    status: str

    model_config = {"from_attributes": True}


class CustomerServiceProductRead(BaseModel):
    id: int
    name: str
    category: str
    brand: Optional[str]
    description: Optional[str]
    selling_points: Optional[str]
    parameters_json: Optional[str]
    shipping_rule_text: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    skus: list[CustomerServiceSKURead] = []

    model_config = {"from_attributes": True}


class CustomerServiceProductListResponse(BaseModel):
    items: list[CustomerServiceProductRead]
    total: int
