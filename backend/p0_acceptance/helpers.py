"""Shared, deliberately small API-contract helpers for P0 acceptance tests.

The test suite owns only this adapter.  When the backend publishes a final
login response schema, update ``login_as`` here rather than duplicating token
assumptions throughout the acceptance tests.
"""

from __future__ import annotations

from typing import Any


AUTH_LOGIN_PATH = "/auth/login"
AUTH_ME_PATH = "/auth/me"
PRODUCTS_PATH = "/api/products"
SKU_COSTS_PATH = "/api/skus/{sku_id}/costs"
SKU_MARGIN_PATH = "/api/skus/{sku_id}/margin"
CONTENT_PACKAGES_PATH = "/api/content/packages"
IMAGE_REFERENCE_PATH = "/api/images/reference"
IMAGE_TASKS_PATH = "/api/images/tasks"
AUDIT_EVENTS_PATH = "/api/audit-events"

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
