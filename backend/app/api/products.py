"""Product management API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_roles
from ..models.user import User
from ..schemas.product import (
    CustomerServiceProductListResponse,
    CustomerServiceProductRead,
    InventoryCreate,
    ProductCreate,
    ProductListResponse,
    ProductRead,
    ProductUpdate,
    SKUCreate,
    SKURead,
    SKUUpdate,
)
from ..services.product_service import (
    add_sku,
    create_product,
    delete_product,
    delete_sku,
    get_product,
    list_products,
    update_inventory,
    update_product,
    update_sku,
)

router = APIRouter(prefix="/api/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=201)
def api_create_product(data: ProductCreate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    return create_product(db, data)


@router.get("", response_model=ProductListResponse | CustomerServiceProductListResponse)
def api_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "operator_content", "customer_service")),
):
    if user.role == "customer_service":
        approved = list_products(db, page=page, page_size=page_size, category=category, status="approved")
        return CustomerServiceProductListResponse(
            items=[CustomerServiceProductRead.model_validate(item) for item in approved.items],
            total=approved.total,
        )
    return list_products(db, page=page, page_size=page_size, category=category, status=status)


@router.get("/{product_id}", response_model=ProductRead | CustomerServiceProductRead)
def api_get_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator_content", "customer_service"))):
    product = get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if user.role == "customer_service":
        if product.status != "approved":
            raise HTTPException(status_code=404, detail={"code":"not_found","message":"Approved product facts not found"})
        return CustomerServiceProductRead.model_validate(product)
    return product


@router.put("/{product_id}", response_model=ProductRead)
def api_update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    product = update_product(db, product_id, data)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/{product_id}", status_code=204)
def api_delete_product(product_id: int, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    if not delete_product(db, product_id):
        raise HTTPException(status_code=404, detail="Product not found")


# --- SKU routes ---

@router.post("/{product_id}/skus", response_model=SKURead, status_code=201)
def api_add_sku(product_id: int, data: SKUCreate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    sku = add_sku(db, product_id, data)
    if not sku:
        raise HTTPException(status_code=404, detail="Product not found")
    return sku


@router.put("/skus/{sku_id}", response_model=SKURead)
def api_update_sku(sku_id: int, data: SKUUpdate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    sku = update_sku(db, sku_id, data)
    if not sku:
        raise HTTPException(status_code=404, detail="SKU not found")
    return sku


@router.delete("/skus/{sku_id}", status_code=204)
def api_delete_sku(sku_id: int, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    if not delete_sku(db, sku_id):
        raise HTTPException(status_code=404, detail="SKU not found")


@router.put("/skus/{sku_id}/inventory")
def api_update_inventory(sku_id: int, data: InventoryCreate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "operator_content"))):
    inv = update_inventory(db, sku_id, data)
    if not inv:
        raise HTTPException(status_code=404, detail="SKU not found")
    return {"sku_id": sku_id, "stock_quantity": inv.stock_quantity}
