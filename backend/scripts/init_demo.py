"""Idempotently initialize the fixed P0 Demo accounts and product facts.

Passwords are required runtime inputs. The command never prints them and does
not provide a weak fallback. Product facts come from the formal docs/demo data
set copied into the image.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models.asset  # noqa: F401
import app.models.content  # noqa: F401
import app.models.order  # noqa: F401

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.cost import SKUCost
from app.models.product import Inventory, Product, SKU
from app.models.user import User

MIN_PASSWORD_LENGTH = 12
ACCOUNTS = (
    ("admin", "admin", "DEMO_ADMIN_PASSWORD"),
    ("operator_content", "operator_content", "DEMO_OPERATOR_PASSWORD"),
    ("customer_service", "customer_service", "DEMO_SERVICE_PASSWORD"),
)
COST_KEYS = {
    "procurement": "purchase_cost",
    "packaging": "packaging_cost",
    "shipping_subsidy": "shipping_subsidy",
    "platform_fee": "platform_fee",
    "promotion_allocation": "marketing_allocation",
    "after_sales_loss": "after_sales_loss",
}


def _required_password(variable: str) -> str:
    value = os.getenv(variable, "")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise SystemExit(
            f"{variable} must be set to at least {MIN_PASSWORD_LENGTH} characters"
        )
    return value


def _demo_file() -> Path:
    configured = os.getenv("DEMO_DATA_FILE")
    candidates = [
        Path(configured) if configured else None,
        BACKEND_ROOT.parent / "docs" / "demo" / "products.json",
        BACKEND_ROOT / "demo" / "products.json",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise SystemExit("Demo product data file was not found")


def main() -> int:
    passwords = {variable: _required_password(variable) for _, _, variable in ACCOUNTS}
    payload = json.loads(_demo_file().read_text(encoding="utf-8"))
    session = SessionLocal()
    created_users = created_products = created_skus = 0
    try:
        for username, role, variable in ACCOUNTS:
            user = session.query(User).filter(User.username == username).first()
            if user is None:
                user = User(username=username)
                session.add(user)
                created_users += 1
            user.role = role
            user.is_active = True
            user.password_hash = hash_password(passwords[variable])

        for source in payload.get("products", []):
            product = session.query(Product).filter(Product.name == source["name"]).first()
            if product is None:
                product = Product(name=source["name"], category=source["category"])
                session.add(product)
                session.flush()
                created_products += 1
            product.category = source["category"]
            product.brand = source.get("brand")
            product.description = source.get("description")
            product.selling_points = "；".join(source.get("selling_points", []))
            product.parameters_json = json.dumps(
                source.get("parameters", {}), ensure_ascii=False, sort_keys=True
            )
            product.shipping_rule_text = source.get("shipping_policy")
            product.status = "approved"
            product.is_deleted = False

            for sku_source in source.get("skus", []):
                sku = (
                    session.query(SKU)
                    .filter(
                        SKU.product_id == product.id,
                        SKU.sku_name == sku_source["name"],
                    )
                    .first()
                )
                if sku is None:
                    sku = SKU(
                        product_id=product.id,
                        sku_name=sku_source["name"],
                        price=sku_source["price"],
                    )
                    session.add(sku)
                    session.flush()
                    created_skus += 1
                sku.size = sku_source.get("size")
                sku.spec = sku_source.get("spec")
                sku.price = sku_source["price"]
                sku.status = "active"
                sku.is_deleted = False

                inventory = (
                    session.query(Inventory).filter(Inventory.sku_id == sku.id).first()
                )
                if inventory is None:
                    inventory = Inventory(sku_id=sku.id)
                    session.add(inventory)
                inventory.stock_quantity = int(sku_source.get("stock", 0))

                cost = session.query(SKUCost).filter(SKUCost.sku_id == sku.id).first()
                if cost is None:
                    cost = SKUCost(sku_id=sku.id)
                    session.add(cost)
                for source_key, field in COST_KEYS.items():
                    setattr(cost, field, sku_source.get("costs", {}).get(source_key))

        session.commit()
        result = {
            "status": "ready",
            "created_users": created_users,
            "created_products": created_products,
            "created_skus": created_skus,
            "roles": [role for _, role, _ in ACCOUNTS],
            "demo_scope": "fixed_closed_dataset",
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())