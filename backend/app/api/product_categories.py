"""First-level product category dictionary API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_roles
from ..models.user import User
from ..schemas.product import (
    ProductCategoryCreate,
    ProductCategoryListResponse,
    ProductCategoryRead,
)
from ..services.product_service import (
    CategoryExistsError,
    create_product_category,
    list_product_categories,
)

router = APIRouter(prefix="/api/product-categories", tags=["product-categories"])


@router.get("", response_model=ProductCategoryListResponse)
def api_list_product_categories(
    db: Session = Depends(get_db),
    _actor: User = Depends(require_roles("admin", "operator_content")),
):
    return list_product_categories(db)


@router.post("", response_model=ProductCategoryRead, status_code=201)
def api_create_product_category(
    data: ProductCategoryCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
):
    try:
        return create_product_category(db, data, actor)
    except CategoryExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "category_exists", "message": "Category already exists"},
        ) from exc
