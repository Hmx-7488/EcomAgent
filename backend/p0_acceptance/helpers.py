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
