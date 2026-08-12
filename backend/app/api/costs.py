"""Six-part SKU cost facts and deterministic estimated-margin API."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_roles
from ..models.content import AuditEvent
from ..models.cost import SKUCost
from ..models.product import SKU
from ..models.user import User
from ..schemas.cost import CostRead, CostWrite, MarginRead

router = APIRouter(prefix="/api/skus", tags=["costs"])
FIELDS = (
    "purchase_cost",
    "packaging_cost",
    "shipping_subsidy",
    "platform_fee",
    "marketing_allocation",
    "after_sales_loss",
)


def cost_view(cost: SKUCost | None, sku_id: int):
    values = {field: getattr(cost, field, None) for field in FIELDS}
    missing = [field for field, value in values.items() if value is None]
    return {
        "sku_id": sku_id,
        **values,
        "completeness": missing,
        "status": "pending_confirmation" if missing else "ready",
    }


def _audit(
    db: Session,
    actor: User,
    action: str,
    sku_id: int,
    *,
    before: dict | None = None,
    after: dict | None = None,
    summary: str,
) -> None:
    db.add(
        AuditEvent(
            action=action,
            target_type="sku",
            target_id=sku_id,
            actor_id=actor.id,
            before_json=json.dumps(before, ensure_ascii=False) if before else None,
            after_json=json.dumps(after, ensure_ascii=False) if after else None,
            summary=summary,
        )
    )


@router.post("/{sku_id}/costs", response_model=CostRead)
def write_cost(
    sku_id: int,
    data: CostWrite,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "operator_content")),
):
    if not db.get(SKU, sku_id):
        raise HTTPException(404, detail={"code": "not_found", "message": "SKU not found"})
    cost = db.query(SKUCost).filter(SKUCost.sku_id == sku_id).first()
    before = cost_view(cost, sku_id)
    if not cost:
        cost = SKUCost(sku_id=sku_id)
        db.add(cost)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cost, field, value)
    db.flush()
    after = cost_view(cost, sku_id)
    _audit(
        db,
        actor,
        "cost.updated",
        sku_id,
        before={"status": before["status"], "missing_fields": before["completeness"]},
        after={"status": after["status"], "missing_fields": after["completeness"]},
        summary="Updated SKU cost facts",
    )
    db.commit()
    db.refresh(cost)
    return after


@router.get("/{sku_id}/margin", response_model=MarginRead)
def margin(
    sku_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "operator_content")),
):
    sku = db.get(SKU, sku_id)
    if not sku:
        raise HTTPException(404, detail={"code": "not_found", "message": "SKU not found"})
    view = cost_view(db.query(SKUCost).filter(SKUCost.sku_id == sku_id).first(), sku_id)
    result = {
        "sku_id": sku_id,
        "sale_price": sku.price,
        "costs": view,
        "total_cost": None,
        "estimated_gross_profit": None,
        "estimated_gross_margin_rate": None,
        "status": view["status"],
    }
    if view["status"] == "ready":
        total = sum(view[field] for field in FIELDS)
        result["total_cost"] = total
        if sku.price > 0:
            profit = sku.price - total
            result.update(
                estimated_gross_profit=profit,
                estimated_gross_margin_rate=profit / sku.price,
            )
        else:
            result["status"] = "pending_confirmation"
    _audit(
        db,
        actor,
        "margin.calculated",
        sku_id,
        after={
            "status": result["status"],
            "total_cost": result["total_cost"],
            "estimated_gross_profit": result["estimated_gross_profit"],
            "estimated_gross_margin_rate": result["estimated_gross_margin_rate"],
        },
        summary="Calculated deterministic estimated margin",
    )
    db.commit()
    return result
