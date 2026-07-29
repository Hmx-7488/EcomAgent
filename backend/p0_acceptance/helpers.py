"""Shared, deliberately small API-contract helpers for P0 acceptance tests.

The test suite owns only this adapter.  When the backend publishes a final
login response schema, update ``login_as`` here rather than duplicating token
assumptions throughout the acceptance tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AUTH_LOGIN_PATH = "/api/auth/login"
AUTH_ME_PATH = "/api/auth/me"
PRODUCTS_PATH = "/api/products"
SKU_COSTS_PATH = "/api/skus/{sku_id}/costs"
SKU_MARGIN_PATH = "/api/skus/{sku_id}/margin"
CONTENT_PACKAGES_PATH = "/api/content/packages"
IMAGE_REFERENCE_PATH = "/api/images/reference"
IMAGE_TASKS_PATH = "/api/images/tasks"
AUDIT_EVENTS_PATH = "/api/audit-events"
CUSTOMER_PRODUCTS_PATH = "/api/customer/products"
CUSTOMER_CONVERSATIONS_PATH = "/api/customer/conversations"
SERVICE_CONVERSATIONS_PATH = "/api/service/conversations"

ROLE_ADMIN = "admin"
ROLE_OPERATOR_CONTENT = "operator_content"
ROLE_CUSTOMER_SERVICE = "customer_service"


REQUIRED_COST_FIELDS = (
    "purchase_cost",
    "packaging_cost",
    "shipping_subsidy",
    "platform_fee",
    "marketing_allocation",
    "after_sales_loss",
)

TEST_PASSWORDS = {
    ROLE_ADMIN: "test-admin-password",
    ROLE_OPERATOR_CONTENT: "test-operator-password",
    ROLE_CUSTOMER_SERVICE: "test-service-password",
}


def error_detail(response: Any) -> dict[str, Any]:
    """Assert and return the frozen P0 error envelope."""
    payload = response.json()
    assert isinstance(payload.get("detail"), dict), payload
    detail = payload["detail"]
    assert isinstance(detail.get("code"), str) and detail["code"], payload
    assert isinstance(detail.get("message"), str) and detail["message"], payload
    return detail


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login_as(client: Any, username: str, password: str) -> dict[str, str]:
    """Log in using the frozen local-account contract."""
    response = client.post(AUTH_LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert isinstance(payload.get("access_token"), str) and payload["access_token"]
    assert payload["user"]["role"] == username
    return bearer_headers(payload["access_token"])


def create_approved_product(client: Any, headers: dict[str, str], *, name: str = "M2 验收商品") -> dict[str, Any]:
    """Create the minimum approved product fact required by M2 generation.

    M2 must never permit content or image generation from a draft product.
    Approval remains a product-fact operation defined by the M1 API.
    """
    created = client.post(
        PRODUCTS_PATH,
        headers=headers,
        json={
            "name": name,
            "category": "Demo",
            "skus": [{"sku_name": "标准款", "price": 100}],
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    approved = client.put(
        f"{PRODUCTS_PATH}/{product['id']}",
        headers=headers,
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def customer_headers(access_token: str) -> dict[str, str]:
    """Build the isolated anonymous-session credential header."""
    return {"X-Conversation-Token": access_token}


def create_customer_conversation(client: Any, product_id: int) -> dict[str, Any]:
    """Create a P0 anonymous conversation and retain its one-time token."""
    response = client.post(CUSTOMER_CONVERSATIONS_PATH, json={"product_id": product_id})
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "open"
    assert isinstance(payload.get("access_token"), str) and len(payload["access_token"]) >= 32
    return payload


def ask_customer(client: Any, conversation: dict[str, Any], content: str) -> dict[str, Any]:
    response = client.post(
        f"{CUSTOMER_CONVERSATIONS_PATH}/{conversation['id']}/messages",
        headers=customer_headers(conversation["access_token"]),
        json={"content": content},
    )
    assert response.status_code == 200, response.text
    return response.json()


def load_demo_json(filename: str) -> Any:
    """Load committed acceptance data without consulting runtime configuration."""
    demo_dir = Path(__file__).resolve().parents[2] / "docs" / "demo"
    return json.loads((demo_dir / filename).read_text(encoding="utf-8"))


def create_approved_demo_product(
    client: Any,
    headers: dict[str, str],
    product_code: str = "ZN-SB-001",
) -> dict[str, Any]:
    """Seed one approved product using only the committed Demo fact source."""
    source = next(
        item for item in load_demo_json("products.json")["products"] if item["code"] == product_code
    )
    created = client.post(
        PRODUCTS_PATH,
        headers=headers,
        json={
            "name": source["name"],
            "category": source["category"],
            "brand": source["brand"],
            "description": source["description"],
            "selling_points": json.dumps(source["selling_points"], ensure_ascii=False),
            "parameters_json": json.dumps(source["parameters"], ensure_ascii=False),
            "shipping_rule_text": source["shipping_policy"],
            "skus": [
                {
                    "sku_name": sku["name"],
                    "color": source["parameters"].get("color"),
                    "size": sku.get("size"),
                    "spec": sku.get("spec"),
                    "price": sku["price"],
                    "inventory": {"stock_quantity": sku["stock"]},
                }
                for sku in source["skus"]
            ],
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    approved = client.put(
        f"{PRODUCTS_PATH}/{product['id']}",
        headers=headers,
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()
