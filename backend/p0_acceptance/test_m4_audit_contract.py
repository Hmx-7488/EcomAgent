"""M4 audit closure for cost facts and deterministic margin calculation."""

from __future__ import annotations

from .helpers import (
    AUDIT_EVENTS_PATH,
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_OPERATOR_CONTENT,
    SKU_COSTS_PATH,
    SKU_MARGIN_PATH,
    TEST_PASSWORDS,
    login_as,
)


def test_cost_update_and_margin_calculation_are_queryable_by_sku(client):
    operator = login_as(client, ROLE_OPERATOR_CONTENT, TEST_PASSWORDS[ROLE_OPERATOR_CONTENT])
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "audit margin product",
            "category": "Demo",
            "skus": [{"sku_name": "SKU", "price": 100}],
        },
    )
    assert created.status_code == 201, created.text
    sku_id = created.json()["skus"][0]["id"]

    costs = {
        "purchase_cost": 30,
        "packaging_cost": 5,
        "shipping_subsidy": 4,
        "platform_fee": 6,
        "marketing_allocation": 10,
        "after_sales_loss": 5,
    }
    assert client.post(
        SKU_COSTS_PATH.format(sku_id=sku_id),
        headers=operator,
        json=costs,
    ).status_code == 200
    assert client.get(
        SKU_MARGIN_PATH.format(sku_id=sku_id),
        headers=operator,
    ).status_code == 200

    admin = login_as(client, ROLE_ADMIN, TEST_PASSWORDS[ROLE_ADMIN])
    audit = client.get(
        AUDIT_EVENTS_PATH,
        headers=admin,
        params={"target_type": "sku", "target_id": sku_id},
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["total"] == 2
    events = {item["action"]: item for item in audit.json()["items"]}
    assert set(events) == {"cost.updated", "margin.calculated"}
    assert all(item["target_type"] == "sku" for item in events.values())
    assert all(item["target_id"] == sku_id for item in events.values())
    assert events["cost.updated"]["actor_id"] is not None
    assert events["margin.calculated"]["actor_id"] is not None
