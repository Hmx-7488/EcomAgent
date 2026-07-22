from typing import Optional
from pydantic import BaseModel, Field
class CostWrite(BaseModel):
    purchase_cost: Optional[float] = Field(None, ge=0)
    packaging_cost: Optional[float] = Field(None, ge=0)
    shipping_subsidy: Optional[float] = Field(None, ge=0)
    platform_fee: Optional[float] = Field(None, ge=0)
    marketing_allocation: Optional[float] = Field(None, ge=0)
    after_sales_loss: Optional[float] = Field(None, ge=0)
class CostRead(CostWrite):
    sku_id: int
    completeness: list[str]
    status: str
class MarginRead(BaseModel):
    sku_id: int; sale_price: float
    costs: CostRead
    total_cost: Optional[float]
    estimated_gross_profit: Optional[float]
    estimated_gross_margin_rate: Optional[float]
    status: str
