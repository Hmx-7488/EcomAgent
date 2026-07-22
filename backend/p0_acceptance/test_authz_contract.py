"""P0 fixed-role authorization acceptance tests.

The authentication adapter is deliberately held in helpers.py until the
backend publishes its exact login schema.  The cases below document the
required authorization matrix without inventing credentials or token fields.
"""

from __future__ import annotations

from .helpers import (
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_CUSTOMER_SERVICE,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    error_detail,
    login_as,
    SKU_COSTS_PATH,
    SKU_MARGIN_PATH,
)


import pytest


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_OPERATOR_CONTENT, ROLE_CUSTOMER_SERVICE])
def test_each_fixed_backoffice_role_can_log_in(client, role):
    """C-F01: exactly the three P0 backoffice roles have local logins."""
    headers = login_as(client, role, TEST_PASSWORDS[role])
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == role


def test_admin_can_maintain_product_facts(client):
    headers = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    response = client.post(
        PRODUCTS_PATH,
        headers=headers,
        json={"name": "管理员商品", "category": "Demo", "skus": []},
    )
    assert response.status_code == 201


def test_operator_content_can_maintain_product_facts(client):
    headers = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    response = client.post(
        PRODUCTS_PATH,
        headers=headers,
        json={"name": "运营商品", "category": "Demo", "skus": []},
    )
    assert response.status_code == 201


def test_customer_service_cannot_edit_product_facts(client):
    headers = login_as(client, ROLE_CUSTOMER_SERVICE, TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE])
    response = client.post(
        PRODUCTS_PATH,
        headers=headers,
        json={"name": "越权商品", "category": "Demo", "skus": []},
    )
    assert response.status_code == 403
    assert error_detail(response)["code"] == "permission_denied"


def test_customer_service_can_read_authorized_product_facts(client):
    """客服可使用已授权事实，但不获得编辑权限。"""
    headers = login_as(client, ROLE_CUSTOMER_SERVICE, TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE])
    response = client.get(PRODUCTS_PATH, headers=headers)
    assert response.status_code == 200


def test_anonymous_customer_cannot_access_backoffice_products(client):
    # The shared legacy fixture authenticates as admin for backward
    # compatibility; send an empty header to exercise the anonymous boundary.
    response = client.get(PRODUCTS_PATH, headers={"Authorization": ""})
    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"]["code"] == "authentication_required"


def test_customer_service_cannot_read_costs_or_margin(client):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={"name": "financial boundary", "category": "Demo", "skus": [{"sku_name": "SKU", "price": 100}]},
    )
    assert created.status_code == 201
    sku_id = created.json()["skus"][0]["id"]
    service = login_as(client, ROLE_CUSTOMER_SERVICE, TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE])
    # Costs are write-only and expose no GET endpoint.  Margin is the
    # financial read endpoint and must reject customer-service credentials.
    assert client.get(SKU_COSTS_PATH.format(sku_id=sku_id), headers=service).status_code == 405
    response = client.get(SKU_MARGIN_PATH.format(sku_id=sku_id), headers=service)
    assert response.status_code == 403
    assert error_detail(response)["code"] == "permission_denied"


def test_customer_service_only_receives_approved_non_financial_facts(client):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={"name": "approved facts", "category": "Demo", "skus": [{"sku_name": "SKU", "price": 100}]},
    )
    product_id = created.json()["id"]
    service = login_as(client, ROLE_CUSTOMER_SERVICE, TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE])
    assert client.get(f"{PRODUCTS_PATH}/{product_id}", headers=service).status_code == 404
    updated = client.put(f"{PRODUCTS_PATH}/{product_id}", headers=operator, json={"status": "approved"})
    assert updated.status_code == 200
    response = client.get(f"{PRODUCTS_PATH}/{product_id}", headers=service)
    assert response.status_code == 200
    sku = response.json()["skus"][0]
    assert "price" not in sku
    assert "inventory" not in sku
