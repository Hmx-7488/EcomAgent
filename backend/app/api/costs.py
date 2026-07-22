from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import require_roles
from ..models.cost import SKUCost
from ..models.product import SKU
from ..schemas.cost import CostWrite, CostRead, MarginRead
router = APIRouter(prefix="/api/skus", tags=["costs"])
FIELDS = ("purchase_cost","packaging_cost","shipping_subsidy","platform_fee","marketing_allocation","after_sales_loss")
def cost_view(cost: SKUCost | None, sku_id: int):
    values = {field: getattr(cost, field, None) for field in FIELDS}
    missing = [field for field, value in values.items() if value is None]
    return {"sku_id":sku_id, **values, "completeness":missing, "status":"pending_confirmation" if missing else "ready"}
@router.post("/{sku_id}/costs", response_model=CostRead)
def write_cost(sku_id: int, data: CostWrite, db: Session = Depends(get_db), _=Depends(require_roles("admin","operator_content"))):
    if not db.get(SKU, sku_id): raise HTTPException(404, detail={"code":"not_found","message":"SKU not found"})
    cost = db.query(SKUCost).filter(SKUCost.sku_id == sku_id).first()
    if not cost: cost = SKUCost(sku_id=sku_id); db.add(cost)
    for field, value in data.model_dump(exclude_unset=True).items(): setattr(cost, field, value)
    db.commit(); db.refresh(cost); return cost_view(cost, sku_id)
@router.get("/{sku_id}/margin", response_model=MarginRead)
def margin(sku_id: int, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    sku = db.get(SKU, sku_id)
    if not sku: raise HTTPException(404, detail={"code":"not_found","message":"SKU not found"})
    view = cost_view(db.query(SKUCost).filter(SKUCost.sku_id == sku_id).first(), sku_id)
    if view["status"] == "pending_confirmation": return {"sku_id":sku_id,"sale_price":sku.price,"costs":view,"total_cost":None,"estimated_gross_profit":None,"estimated_gross_margin_rate":None,"status":view["status"]}
    total = sum(view[field] for field in FIELDS); profit = sku.price-total
    return {"sku_id":sku_id,"sale_price":sku.price,"costs":view,"total_cost":total,"estimated_gross_profit":profit,"estimated_gross_margin_rate":profit/sku.price,"status":"ready"}
