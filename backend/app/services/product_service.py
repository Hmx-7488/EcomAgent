"""CRUD operations for products, SKUs, and inventory."""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..models.product import Inventory, Product, SKU
from ..schemas.product import (
    InventoryCreate,
    ProductCreate,
    ProductListResponse,
    ProductRead,
    ProductUpdate,
    SKUCreate,
    SKUUpdate,
)


def create_product(db: Session, data: ProductCreate) -> Product:
    product = Product(
        name=data.name,
        category=data.category,
        brand=data.brand,
        description=data.description,
        selling_points=data.selling_points,
        parameters_json=data.parameters_json,
        shipping_rule_text=data.shipping_rule_text,
    )
    db.add(product)
    db.flush()  # get product.id for SKUs

    for sku_data in data.skus:
        sku = _create_sku(db, product.id, sku_data)
        db.add(sku)

    db.commit()
    db.refresh(product)
    return product


def _active_product_query(db: Session):
    """Base query that excludes soft-deleted products."""
    return db.query(Product).filter(Product.is_deleted == False)


def get_product(db: Session, product_id: int) -> Optional[Product]:
    return (
        _active_product_query(db)
        .options(joinedload(Product.skus).joinedload(SKU.inventory))
        .filter(Product.id == product_id)
        .first()
    )


def list_products(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> ProductListResponse:
    query = _active_product_query(db)
    if category:
        query = query.filter(Product.category == category)
    if status:
        query = query.filter(Product.status == status)

    total = query.count()
    items = (
        query.options(joinedload(Product.skus).joinedload(SKU.inventory))
        .order_by(Product.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ProductListResponse(
        items=[ProductRead.model_validate(p) for p in items], total=total
    )


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Optional[Product]:
    product = _active_product_query(db).filter(Product.id == product_id).first()
    if not product:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int) -> bool:
    """Soft-delete: set is_deleted=True and status='deleted'."""
    product = _active_product_query(db).filter(Product.id == product_id).first()
    if not product:
        return False
    product.is_deleted = True
    product.status = "deleted"
    db.commit()
    return True


# --- SKU ---

def _create_sku(db: Session, product_id: int, data: SKUCreate) -> SKU:
    sku = SKU(
        product_id=product_id,
        sku_name=data.sku_name,
        color=data.color,
        size=data.size,
        spec=data.spec,
        price=data.price,
        image_url=data.image_url,
    )
    # Persist SKU first so its generated primary key can be used by inventory.
    db.add(sku)
    db.flush()

    if data.inventory:
        inv = Inventory(
            sku_id=sku.id,
            stock_quantity=data.inventory.stock_quantity,
            locked_quantity=data.inventory.locked_quantity,
            safety_stock=data.inventory.safety_stock,
        )
        db.add(inv)

    return sku


def _active_sku_query(db: Session):
    """Base query that excludes soft-deleted SKUs."""
    return db.query(SKU).filter(SKU.is_deleted == False)


def add_sku(db: Session, product_id: int, data: SKUCreate) -> Optional[SKU]:
    product = _active_product_query(db).filter(Product.id == product_id).first()
    if not product:
        return None
    sku = _create_sku(db, product_id, data)
    db.commit()
    db.refresh(sku)
    return sku


def update_sku(db: Session, sku_id: int, data: SKUUpdate) -> Optional[SKU]:
    sku = _active_sku_query(db).filter(SKU.id == sku_id).first()
    if not sku:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(sku, key, value)
    db.commit()
    db.refresh(sku)
    return sku


def delete_sku(db: Session, sku_id: int) -> bool:
    """Soft-delete: set is_deleted=True and status='deleted'."""
    sku = _active_sku_query(db).filter(SKU.id == sku_id).first()
    if not sku:
        return False
    sku.is_deleted = True
    sku.status = "deleted"
    db.commit()
    return True


def update_inventory(
    db: Session, sku_id: int, data: InventoryCreate
) -> Optional[Inventory]:
    if not _active_sku_query(db).filter(SKU.id == sku_id).first():
        return None
    inv = db.query(Inventory).filter(Inventory.sku_id == sku_id).first()
    if not inv:
        inv = Inventory(sku_id=sku_id, stock_quantity=0)
        db.add(inv)
        db.flush()
    inv.stock_quantity = data.stock_quantity
    inv.locked_quantity = data.locked_quantity
    inv.safety_stock = data.safety_stock
    db.commit()
    db.refresh(inv)
    return inv
