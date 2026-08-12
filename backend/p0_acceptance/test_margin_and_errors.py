"""Milestone 1 API acceptance tests: cost facts, margin, and error contract.

These tests are intentionally separate from legacy tests.  They define the
frozen P0 contract and may be red until the Milestone 1 backend is integrated.
"""

from __future__ import annotations

import socket

import pytest

from .helpers import (
    PRODUCTS_PATH,
    REQUIRED_COST_FIELDS,
    SKU_COSTS_PATH,
    SKU_MARGIN_PATH,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    error_detail,
    login_as,
)


@pytest.fixture(autouse=True)
def deny_external_network(monkeypatch):
    """Any attempted network egress fails the test rather than silently using it."""
    real_connect = socket.socket.connect

    def blocked_create_connection(*args, **kwargs):
        pytest.fail("P0 acceptance tests must not access the network")

    def guarded_connect(sock, address):
        # TestClient uses loopback/in-process socket plumbing.  Permit only
        # that local transport; TCP connections to every other host are test
        # failures.  Unix/local socket addresses are also local transports.
        if isinstance(address, str):
            return real_connect(sock, address)
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
            return real_connect(sock, address)
        pytest.fail("P0 acceptance tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", blocked_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


def _operator_headers(client):
    return login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])


def _create_product_with_sku(client, price: float = 100.0, headers=None) -> int:
    headers = headers or _operator_headers(client)
    response = client.post(
        PRODUCTS_PATH,
        headers=headers,
        json={
            "name": "P0 毛利验收商品",
            "category": "Demo",
            "skus": [{"sku_name": "标准款", "price": price}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["skus"][0]["id"]


def _complete_cost_payload() -> dict[str, float]:
    return {
        "purchase_cost": 30.0,
        "packaging_cost": 5.0,
        "shipping_subsidy": 4.0,
        "platform_fee": 6.0,
        "marketing_allocation": 10.0,
        "after_sales_loss": 5.0,
    }


def test_complete_costs_return_deterministic_margin(client):
    """C-F02/C-Q07: (100 - 30 - 5 - 4 - 6 - 10 - 5) / 100 == 0.40."""
    headers = _operator_headers(client)
    sku_id = _create_product_with_sku(client, price=100.0, headers=headers)
    write = client.post(SKU_COSTS_PATH.format(sku_id=sku_id), headers=headers, json=_complete_cost_payload())
    assert write.status_code in {200, 201}, write.text

    response = client.get(SKU_MARGIN_PATH.format(sku_id=sku_id), headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["sale_price"] == pytest.approx(100.0)
    assert payload["estimated_gross_profit"] == pytest.approx(40.0)
    assert payload["estimated_gross_margin_rate"] == pytest.approx(0.4)


@pytest.mark.parametrize("missing_field", REQUIRED_COST_FIELDS)
def test_any_missing_required_cost_is_pending_confirmation(client, missing_field):
    """C-Q07: no partial cost calculation may become a usable margin result."""
    headers = _operator_headers(client)
    sku_id = _create_product_with_sku(client, headers=headers)
    costs = _complete_cost_payload()
    costs.pop(missing_field)
    write = client.post(SKU_COSTS_PATH.format(sku_id=sku_id), headers=headers, json=costs)
    assert write.status_code in {200, 201, 422}, write.text

    response = client.get(SKU_MARGIN_PATH.format(sku_id=sku_id), headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "pending_confirmation"
    assert payload.get("estimated_gross_profit") is None
    assert payload.get("estimated_gross_margin_rate") is None


def test_zero_received_price_is_persisted(client):
    response = client.post(
        PRODUCTS_PATH,
        headers=_operator_headers(client),
        json={"name": "零价商品", "category": "Demo", "skus": [{"sku_name": "SKU", "price": 0}]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["skus"][0]["price"] == 0


def test_zero_received_price_can_update_an_existing_sku(client):
    headers = _operator_headers(client)
    sku_id = _create_product_with_sku(client, price=100, headers=headers)
    response = client.put(
        f"{PRODUCTS_PATH}/skus/{sku_id}",
        headers=headers,
        json={"price": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["price"] == 0


@pytest.mark.parametrize("price", [-0.01, -100])
def test_negative_received_price_is_rejected_on_create(client, price):
    response = client.post(
        PRODUCTS_PATH,
        headers=_operator_headers(client),
        json={"name": "无效价格", "category": "Demo", "skus": [{"sku_name": "SKU", "price": price}]},
    )
    assert response.status_code == 422
    assert error_detail(response)["code"] == "validation_error"


def test_negative_received_price_is_rejected_on_update(client):
    headers = _operator_headers(client)
    sku_id = _create_product_with_sku(client, headers=headers)
    response = client.put(
        f"{PRODUCTS_PATH}/skus/{sku_id}", headers=headers, json={"price": -0.01}
    )
    assert response.status_code == 422
    assert error_detail(response)["code"] == "validation_error"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_received_price_is_rejected_by_create_and_update_schemas(value):
    from pydantic import ValidationError

    from app.schemas.product import SKUCreate, SKUUpdate

    with pytest.raises(ValidationError):
        SKUCreate(sku_name="SKU", price=value)
    with pytest.raises(ValidationError):
        SKUUpdate(price=value)


def test_zero_price_with_complete_costs_keeps_total_but_not_margin(client):
    headers = _operator_headers(client)
    sku_id = _create_product_with_sku(client, price=0, headers=headers)
    costs = _complete_cost_payload()
    write = client.post(
        SKU_COSTS_PATH.format(sku_id=sku_id), headers=headers, json=costs
    )
    assert write.status_code == 200, write.text

    response = client.get(SKU_MARGIN_PATH.format(sku_id=sku_id), headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "pending_confirmation"
    assert payload["total_cost"] == pytest.approx(sum(costs.values()))
    assert payload["estimated_gross_profit"] is None
    assert payload["estimated_gross_margin_rate"] is None


@pytest.mark.parametrize("field", REQUIRED_COST_FIELDS)
def test_negative_cost_is_rejected(client, field):
    headers = _operator_headers(client)
    sku_id = _create_product_with_sku(client, headers=headers)
    costs = _complete_cost_payload()
    costs[field] = -0.01
    response = client.post(SKU_COSTS_PATH.format(sku_id=sku_id), headers=headers, json=costs)
    assert response.status_code == 422
    assert error_detail(response)["code"] == "validation_error"


def test_unknown_resource_uses_uniform_not_found_error(client):
    response = client.get(SKU_MARGIN_PATH.format(sku_id=999999), headers=_operator_headers(client))
    assert response.status_code == 404
    assert error_detail(response)["code"] == "not_found"


def test_unknown_route_uses_uniform_not_found_error(client):
    response = client.get("/not-a-p0-endpoint")
    assert response.status_code == 404
    assert error_detail(response)["code"] == "not_found"
