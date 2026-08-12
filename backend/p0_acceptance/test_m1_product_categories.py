"""P0 maintenance contract for the first-level product category dictionary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from .helpers import (
    PRODUCTS_PATH,
    ROLE_ADMIN,
    ROLE_CUSTOMER_SERVICE,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    error_detail,
    login_as,
)


CATEGORIES_PATH = "/api/product-categories"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260811_05_product_categories.py"
)


def _headers(client, role: str) -> dict[str, str]:
    return login_as(client, role, TEST_PASSWORDS[role])


def _create_category(client, name: str = "电子产品") -> dict:
    response = client.post(
        CATEGORIES_PATH,
        headers=_headers(client, ROLE_ADMIN),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _load_migration():
    assert MIGRATION_PATH.is_file(), "the approved 20260811_05 migration is missing"
    spec = importlib.util.spec_from_file_location("product_categories_05", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FORBIDDEN_VALIDATION_KEYS = {"ctx", "type", "loc", "input", "url"}


def _response_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(
            *( _response_keys(item) for item in value.values() )
        )
    if isinstance(value, list):
        return set().union(*( _response_keys(item) for item in value ))
    return set()


def _assert_safe_validation_payload(
    payload: dict,
    *,
    expected_fields: set[str],
    forbidden_text: tuple[str, ...] = (),
) -> None:
    detail = payload["detail"]
    assert detail["code"] == "validation_error"
    assert detail["message"] == "请求参数校验失败"
    assert detail["fields"]
    assert all(set(field) == {"field", "message"} for field in detail["fields"])
    assert expected_fields <= {field["field"] for field in detail["fields"]}
    assert not (FORBIDDEN_VALIDATION_KEYS & _response_keys(payload))

    serialized = json.dumps(payload, ensure_ascii=False)
    for token in (
        "greater_than_equal",
        "string_too_long",
        "finite_number",
        "Request validation failed",
        '"body"',
        *forbidden_text,
    ):
        assert token not in serialized


def test_global_validation_errors_return_only_safe_chinese_fields(client):
    negative = client.post(
        PRODUCTS_PATH,
        json={
            "name": "安全错误商品",
            "category": "Demo",
            "skus": [{"sku_name": "标准款", "price": -77.25}],
        },
    )
    assert negative.status_code == 422
    _assert_safe_validation_payload(
        negative.json(),
        expected_fields={"第1个SKU零售价"},
        forbidden_text=("-77.25",),
    )

    overlong_name = "RAW_INVALID_SENTINEL_" + "x" * 129
    overlong = client.post(CATEGORIES_PATH, json={"name": overlong_name})
    assert overlong.status_code == 422
    _assert_safe_validation_payload(
        overlong.json(),
        expected_fields={"类目名称"},
        forbidden_text=("RAW_INVALID_SENTINEL_", overlong_name),
    )

    blank = client.post(CATEGORIES_PATH, json={"name": "   "})
    assert blank.status_code == 422
    _assert_safe_validation_payload(blank.json(), expected_fields={"类目名称"})


def test_missing_and_non_finite_values_use_safe_nested_field_names(client):
    missing = client.post(PRODUCTS_PATH, json={})
    assert missing.status_code == 422
    _assert_safe_validation_payload(
        missing.json(), expected_fields={"商品名称", "商品类目"}
    )

    non_finite = client.post(
        PRODUCTS_PATH,
        json={
            "name": "非有限价格商品",
            "category": "Demo",
            "skus": [{"sku_name": "标准款", "price": "NaN"}],
        },
    )
    assert non_finite.status_code == 422
    _assert_safe_validation_payload(
        non_finite.json(),
        expected_fields={"第1个SKU零售价"},
        forbidden_text=("NaN",),
    )


def test_unknown_validation_location_and_type_use_a_safe_fallback():
    import asyncio
    from types import SimpleNamespace

    from fastapi.exceptions import RequestValidationError

    from app.main import validation_error_handler

    request = SimpleNamespace(url=SimpleNamespace(path="/api/unknown"))
    exception = RequestValidationError(
        [
            {
                "type": "internal_python_validator_type",
                "loc": ("body", "private", "RAW_PATH_SENTINEL"),
                "msg": "Internal validation implementation detail",
                "input": "RAW_INPUT_SENTINEL",
                "ctx": {"exception": "RAW_EXCEPTION_SENTINEL"},
                "url": "https://internal.invalid/error",
            }
        ]
    )
    response = asyncio.run(validation_error_handler(request, exception))
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload == {
        "detail": {
            "code": "validation_error",
            "message": "请求参数校验失败",
            "fields": [
                {"field": "请求参数", "message": "输入内容不符合要求"}
            ],
        }
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    for token in (
        "RAW_PATH_SENTINEL",
        "RAW_INPUT_SENTINEL",
        "RAW_EXCEPTION_SENTINEL",
        "internal_python_validator_type",
        "internal.invalid",
    ):
        assert token not in serialized


@pytest.mark.parametrize(
    ("error_type", "path", "location", "expected_field", "expected_message"),
    [
        ("missing", "/api/products", ("body", "name"), "商品名称", "请填写商品名称"),
        (
            "string_too_short",
            CATEGORIES_PATH,
            ("body", "name"),
            "类目名称",
            "类目名称不能为空",
        ),
        (
            "string_too_long",
            CATEGORIES_PATH,
            ("body", "name"),
            "类目名称",
            "类目名称长度超出限制",
        ),
        (
            "greater_than_equal",
            "/api/products",
            ("body", "skus", 1, "price"),
            "第2个SKU零售价",
            "第2个SKU零售价不能小于0",
        ),
        (
            "finite_number",
            "/api/products",
            ("body", "skus", 0, "price"),
            "第1个SKU零售价",
            "第1个SKU零售价必须是有限数字",
        ),
        (
            "float_parsing",
            "/api/products",
            ("body", "skus", 0, "price"),
            "第1个SKU零售价",
            "第1个SKU零售价必须是有效数字",
        ),
        (
            "int_parsing",
            "/api/products",
            ("body", "skus", 0, "inventory", "stock_quantity"),
            "第1个SKU库存数量",
            "第1个SKU库存数量必须是整数",
        ),
        ("list_type", "/api/products", ("body", "skus"), "SKU列表", "SKU列表必须是列表"),
        (
            "dict_type",
            "/api/products",
            ("body", "skus", 0, "inventory"),
            "第1个SKU库存信息",
            "第1个SKU库存信息格式不正确",
        ),
        ("enum", "/api/products", ("body", "status"), "状态", "状态的取值不符合要求"),
        (
            "literal_error",
            "/api/content/packages",
            ("body", "content_type"),
            "内容类型",
            "内容类型的取值不符合要求",
        ),
    ],
)
def test_supported_validation_types_are_mapped_without_raw_metadata(
    error_type, path, location, expected_field, expected_message
):
    import asyncio
    from types import SimpleNamespace

    from fastapi.exceptions import RequestValidationError

    from app.main import validation_error_handler

    request = SimpleNamespace(url=SimpleNamespace(path=path))
    exception = RequestValidationError(
        [
            {
                "type": error_type,
                "loc": location,
                "msg": "RAW_INTERNAL_MESSAGE",
                "input": "RAW_INVALID_VALUE",
                "ctx": {"internal": "RAW_INTERNAL_CONTEXT"},
                "url": "https://internal.invalid/error",
            }
        ]
    )
    response = asyncio.run(validation_error_handler(request, exception))
    payload = json.loads(response.body)

    _assert_safe_validation_payload(
        payload,
        expected_fields={expected_field},
        forbidden_text=(
            error_type,
            "RAW_INTERNAL_MESSAGE",
            "RAW_INVALID_VALUE",
            "RAW_INTERNAL_CONTEXT",
        ),
    )
    assert payload["detail"]["fields"] == [
        {"field": expected_field, "message": expected_message}
    ]


def test_category_read_rbac_and_active_stable_order(client, db_session):
    from app.models.product import ProductCategory

    db_session.add_all(
        [
            ProductCategory(name="桌面收纳", is_active=True),
            ProductCategory(name="旅行收纳", is_active=True),
            ProductCategory(name="停用类目", is_active=False),
        ]
    )
    db_session.commit()

    for role in (ROLE_ADMIN, ROLE_OPERATOR_CONTENT):
        response = client.get(CATEGORIES_PATH, headers=_headers(client, role))
        assert response.status_code == 200, response.text
        payload = response.json()
        names = [item["name"] for item in payload["items"]]
        assert payload["total"] == len(names)
        assert names == sorted(names)
        assert {"旅行收纳", "桌面收纳"} <= set(names)
        assert "停用类目" not in names
        assert all(item["is_active"] for item in payload["items"])

    forbidden = client.get(
        CATEGORIES_PATH,
        headers=_headers(client, ROLE_CUSTOMER_SERVICE),
    )
    assert forbidden.status_code == 403
    assert error_detail(forbidden)["code"] == "permission_denied"
    anonymous = client.get(CATEGORIES_PATH, headers={"Authorization": ""})
    assert anonymous.status_code == 401
    assert error_detail(anonymous)["code"] == "authentication_required"


def test_category_create_rbac_validation_duplicate_and_audit(client, db_session):
    from app.models.content import AuditEvent

    created = client.post(
        CATEGORIES_PATH,
        headers=_headers(client, ROLE_ADMIN),
        json={"name": "  Storage  "},
    )
    assert created.status_code == 201, created.text
    category = created.json()
    assert category["name"] == "Storage"
    assert category["is_active"] is True

    audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "category.created",
            AuditEvent.target_type == "product_category",
            AuditEvent.target_id == category["id"],
        )
        .all()
    )
    assert len(audit) == 1
    assert "Storage" not in (audit[0].before_json or "")
    assert "Storage" not in (audit[0].after_json or "")

    duplicate = client.post(
        CATEGORIES_PATH,
        headers=_headers(client, ROLE_ADMIN),
        json={"name": " Storage "},
    )
    assert duplicate.status_code == 409
    assert error_detail(duplicate)["code"] == "category_exists"
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "category.created")
        .count()
        == 1
    )

    case_sensitive = client.post(
        CATEGORIES_PATH,
        headers=_headers(client, ROLE_ADMIN),
        json={"name": "storage"},
    )
    assert case_sensitive.status_code == 201, case_sensitive.text

    for invalid_name in ("   ", "x" * 129):
        invalid = client.post(
            CATEGORIES_PATH,
            headers=_headers(client, ROLE_ADMIN),
            json={"name": invalid_name},
        )
        assert invalid.status_code == 422
        assert error_detail(invalid)["code"] == "validation_error"

    for role in (ROLE_OPERATOR_CONTENT, ROLE_CUSTOMER_SERVICE):
        forbidden = client.post(
            CATEGORIES_PATH,
            headers=_headers(client, role),
            json={"name": f"forbidden-{role}"},
        )
        assert forbidden.status_code == 403
        assert error_detail(forbidden)["code"] == "permission_denied"


def test_products_require_an_active_dictionary_category(client, db_session):
    from app.models.product import ProductCategory

    active = _create_category(client, "桌面收纳")
    db_session.add(ProductCategory(name="停用类目", is_active=False))
    db_session.commit()
    operator = _headers(client, ROLE_OPERATOR_CONTENT)

    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "类目契约商品",
            "category": active["name"],
            "skus": [{"sku_name": "标准款", "price": 0}],
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    assert created.json()["category"] == "桌面收纳"

    for invalid_category in ("未知类目", "停用类目"):
        rejected = client.post(
            PRODUCTS_PATH,
            headers=operator,
            json={"name": "无效类目商品", "category": invalid_category, "skus": []},
        )
        assert rejected.status_code == 422
        assert error_detail(rejected)["code"] == "category_not_found"

        update = client.put(
            f"{PRODUCTS_PATH}/{product_id}",
            headers=operator,
            json={"category": invalid_category},
        )
        assert update.status_code == 422
        assert error_detail(update)["code"] == "category_not_found"

    unchanged = client.get(f"{PRODUCTS_PATH}/{product_id}", headers=operator)
    assert unchanged.status_code == 200
    assert unchanged.json()["category"] == "桌面收纳"


def test_customer_service_product_projection_remains_non_financial(client):
    _create_category(client, "客服可见类目")
    operator = _headers(client, ROLE_OPERATOR_CONTENT)
    created = client.post(
        PRODUCTS_PATH,
        headers=operator,
        json={
            "name": "客服裁剪回归",
            "category": "客服可见类目",
            "skus": [{"sku_name": "标准款", "price": 0}],
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    assert client.put(
        f"{PRODUCTS_PATH}/{product_id}",
        headers=operator,
        json={"status": "approved"},
    ).status_code == 200

    service = _headers(client, ROLE_CUSTOMER_SERVICE)
    response = client.get(f"{PRODUCTS_PATH}/{product_id}", headers=service)
    assert response.status_code == 200
    assert response.json()["category"] == "客服可见类目"
    assert "price" not in response.json()["skus"][0]
    assert "inventory" not in response.json()["skus"][0]


def test_migration_upgrade_backfills_trimmed_distinct_names_and_downgrades():
    migration = _load_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.execute(
            text(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, "
                "category VARCHAR(128) NOT NULL)"
            )
        )
        connection.execute(text("CREATE TABLE audit_events (id INTEGER PRIMARY KEY, action VARCHAR(64))"))
        connection.execute(
            text(
                "INSERT INTO products (id, name, category) VALUES "
                "(1, 'A', ' 桌面收纳 '), (2, 'B', '桌面收纳'), "
                "(3, 'C', '居家收纳用品/旅行收纳'), (4, 'D', '   ')"
            )
        )
        connection.execute(text("INSERT INTO audit_events (id, action) VALUES (1, 'sentinel')"))
        before_products = connection.execute(
            text("SELECT id, name, category FROM products ORDER BY id")
        ).all()
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        assert "product_categories" in inspect(connection).get_table_names()
        assert connection.execute(
            text("SELECT name FROM product_categories ORDER BY name")
        ).scalars().all() == ["居家收纳用品/旅行收纳", "桌面收纳"]
        assert connection.execute(
            text("SELECT id, name, category FROM products ORDER BY id")
        ).all() == before_products
        assert connection.execute(text("SELECT action FROM audit_events")).scalar_one() == "sentinel"

        with Operations.context(context):
            migration.downgrade()
        assert "product_categories" not in inspect(connection).get_table_names()
        assert connection.execute(
            text("SELECT id, name, category FROM products ORDER BY id")
        ).all() == before_products
        assert connection.execute(text("SELECT action FROM audit_events")).scalar_one() == "sentinel"
    engine.dispose()


def test_demo_initialization_creates_categories_idempotently(
    db_session, monkeypatch, tmp_path
):
    from scripts import init_demo

    demo_file = tmp_path / "products.json"
    demo_file.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "name": "幂等Demo商品",
                        "category": "居家收纳用品/桌面收纳",
                        "brand": "Demo",
                        "skus": [
                            {
                                "name": "标准款",
                                "price": 0,
                                "stock": 0,
                                "costs": {},
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(init_demo, "SessionLocal", factory)
    monkeypatch.setenv("DEMO_DATA_FILE", str(demo_file))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "demo-admin-password")
    monkeypatch.setenv("DEMO_OPERATOR_PASSWORD", "demo-operator-password")
    monkeypatch.setenv("DEMO_SERVICE_PASSWORD", "demo-service-password")

    assert init_demo.main() == 0
    assert init_demo.main() == 0

    from app.models.product import Product, ProductCategory

    with factory() as session:
        assert (
            session.query(ProductCategory)
            .filter(ProductCategory.name == "居家收纳用品/桌面收纳")
            .count()
            == 1
        )
        assert session.query(Product).filter(Product.name == "幂等Demo商品").count() == 1
