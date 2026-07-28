"""Public customer and protected service-workbench contracts for P0 M3."""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


def _trim_required(value: str) -> str:
    if isinstance(value, str):
        value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value

class ProductRef(BaseModel):
    id: int
    name: str

class CustomerProductRead(ProductRef):
    category: str
    brand: Optional[str] = None
    summary: Optional[str] = None
    status: str

class CustomerProductListResponse(BaseModel):
    items: list[CustomerProductRead]
    total: int

class ConversationCreate(BaseModel):
    product_id: int = Field(gt=0)

class CustomerMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    _normalize_content = field_validator("content", mode="before")(_trim_required)

class PublicMessage(BaseModel):
    id: int
    sender_type: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}

class ConversationCreated(BaseModel):
    id: int
    status: str
    product: ProductRef
    access_token: str
    created_at: datetime
    reason_code: Optional[str] = None

class CustomerConversationRead(BaseModel):
    id: int
    status: str
    product: ProductRef
    reason_code: Optional[str] = None
    messages: list[PublicMessage]
    created_at: datetime
    updated_at: datetime

class CustomerMessageResult(BaseModel):
    conversation_id: int
    status: str
    risk_level: Literal["low", "medium", "high"]
    decision: Literal["auto_reply", "review_draft", "transfer"]
    reason_code: str
    customer_message: PublicMessage
    reply: Optional[PublicMessage] = None
    notice: Optional[PublicMessage] = None
    source_summary: list[dict]

class ServiceSendRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    _normalize_content = field_validator("content", mode="before")(_trim_required)

class ServiceTransferRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    _normalize_reason = field_validator("reason", mode="before")(_trim_required)
