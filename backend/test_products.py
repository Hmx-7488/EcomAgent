"""Tests for product CRUD API."""


from p0_acceptance.helpers import (
    ROLE_CUSTOMER_SERVICE,
    ROLE_OPERATOR_CONTENT,
    TEST_PASSWORDS,
    login_as,
)


class TestProductCreate:
    def test_create_product_success(self, client):
        payload = {
            "name": "测试商品",
            "category": "数码",
            "brand": "测试品牌",
            "skus": [
                {
                    "sku_name": "黑色-M",
                    "color": "黑色",
                    "size": "M",
                    "price": 99.0,
                    "inventory": {
                        "stock_quantity": 100,
                        "locked_quantity": 0,
                        "safety_stock": 10,
                    },
                }
            ],
        }
        resp = client.post("/api/products", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试商品"
        assert data["category"] == "数码"
        assert len(data["skus"]) == 1
        assert data["skus"][0]["price"] == 99.0
        assert data["skus"][0]["inventory"]["stock_quantity"] == 100

    def test_create_product_missing_name(self, client):
        resp = client.post("/api/products", json={"category": "数码"})
        assert resp.status_code == 422


class TestProductList:
    def test_list_empty(self, client):
        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_after_create(self, client):
        client.post("/api/products", json={
            "name": "商品A", "category": "服装",
            "skus": [{"sku_name": "红-S", "size": "S", "color": "红色", "price": 50}]
        })
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestProductSoftDelete:
    def test_soft_delete_product(self, client):
        # Create
        resp = client.post("/api/products", json={
            "name": "待删除", "category": "食品",
            "skus": [{"sku_name": "默认", "price": 10}]
        })
        product_id = resp.json()["id"]

        # Delete (soft)
        resp = client.delete(f"/api/products/{product_id}")
        assert resp.status_code == 204

        # Should not appear in list
        resp = client.get("/api/products")
        assert resp.json()["total"] == 0

        # Direct GET should also 404
        resp = client.get(f"/api/products/{product_id}")
        assert resp.status_code == 404


class TestSKUOperations:
    def test_add_sku(self, client):
        resp = client.post("/api/products", json={
            "name": "SKU测试", "category": "鞋类",
            "skus": [{"sku_name": "40码", "price": 299}]
        })
        product_id = resp.json()["id"]

        resp = client.post(f"/api/products/{product_id}/skus", json={
            "sku_name": "41码", "color": "白", "price": 299,
            "inventory": {"stock_quantity": 50}
        })
        assert resp.status_code == 201

    def test_soft_delete_sku(self, client):
        resp = client.post("/api/products", json={
            "name": "SKU删除测试", "category": "鞋类",
            "skus": [{"sku_name": "40码", "price": 299}]
        })
        sku_id = resp.json()["skus"][0]["id"]

        resp = client.delete(f"/api/products/skus/{sku_id}")
        assert resp.status_code == 204

    def test_sku_price_zero_accepted_without_margin_result(self, client):
        """Zero is a valid price, but estimated margin stays pending."""
        resp = client.post("/api/products", json={
            "name": "价格边界测试", "category": "测试",
            "skus": [{"sku_name": "免费版", "price": 0}]
        })
        assert resp.status_code == 201
        sku = resp.json()["skus"][0]
        assert sku["price"] == 0

        margin = client.get(f"/api/skus/{sku['id']}/margin")
        assert margin.status_code == 200
        assert margin.json()["status"] == "pending_confirmation"
        assert margin.json()["estimated_gross_profit"] is None
        assert margin.json()["estimated_gross_margin_rate"] is None

    def test_sku_price_can_be_updated_to_zero_without_margin_result(self, client):
        """The SKU update contract accepts and persists an exact zero price."""
        created = client.post("/api/products", json={
            "name": "零价更新测试", "category": "测试",
            "skus": [{"sku_name": "标准版", "price": 10}]
        })
        assert created.status_code == 201
        sku_id = created.json()["skus"][0]["id"]

        updated = client.put(
            f"/api/products/skus/{sku_id}",
            json={"price": 0},
        )
        assert updated.status_code == 200
        assert updated.json()["price"] == 0

        margin = client.get(f"/api/skus/{sku_id}/margin")
        assert margin.status_code == 200
        assert margin.json()["status"] == "pending_confirmation"
        assert margin.json()["estimated_gross_profit"] is None
        assert margin.json()["estimated_gross_margin_rate"] is None

    def test_sku_price_negative_rejected(self, client):
        """Negative prices must be rejected."""
        resp = client.post("/api/products", json={
            "name": "负价测试", "category": "测试",
            "skus": [{"sku_name": "倒贴", "price": -1}]
        })
        assert resp.status_code == 422

    def test_sku_price_positive_accepted(self, client):
        """Valid price > 0 must be accepted."""
        resp = client.post("/api/products", json={
            "name": "正常价格", "category": "测试",
            "skus": [{"sku_name": "标准版", "price": 0.01}]
        })
        assert resp.status_code == 201


class TestSKUUpdate:
    def test_update_sku_name(self, client):
        resp = client.post("/api/products", json={
            "name": "SKU更新测试", "category": "数码",
            "skus": [{"sku_name": "原名称", "price": 50}]
        })
        sku_id = resp.json()["skus"][0]["id"]

        resp = client.put(f"/api/products/skus/{sku_id}", json={
            "sku_name": "新名称"
        })
        assert resp.status_code == 200
        assert resp.json()["sku_name"] == "新名称"

    def test_update_sku_price(self, client):
        resp = client.post("/api/products", json={
            "name": "SKU改价", "category": "服装",
            "skus": [{"sku_name": "标准版", "price": 99}]
        })
        sku_id = resp.json()["skus"][0]["id"]

        resp = client.put(f"/api/products/skus/{sku_id}", json={
            "price": 149.99
        })
        assert resp.status_code == 200
        assert resp.json()["price"] == 149.99

    def test_update_sku_not_found(self, client):
        resp = client.put("/api/products/skus/99999", json={
            "sku_name": "不存在的SKU"
        })
        assert resp.status_code == 404

    def test_update_deleted_sku_rejected(self, client):
        """Soft-deleted SKU should not be updateable."""
        resp = client.post("/api/products", json={
            "name": "删除后更新", "category": "测试",
            "skus": [{"sku_name": "待删SKU", "price": 10}]
        })
        sku_id = resp.json()["skus"][0]["id"]

        # Soft-delete first
        client.delete(f"/api/products/skus/{sku_id}")

        # Attempt update on deleted SKU
        resp = client.put(f"/api/products/skus/{sku_id}", json={
            "sku_name": "尝试更新"
        })
        assert resp.status_code == 404


class TestSKUMaintenanceRoles:
    def test_operator_can_create_and_update_sku_facts(self, client):
        product = client.post(
            "/api/products",
            json={"name": "SKU权限测试", "category": "测试", "skus": []},
        )
        assert product.status_code == 201
        product_id = product.json()["id"]
        operator = login_as(
            client,
            ROLE_OPERATOR_CONTENT,
            TEST_PASSWORDS[ROLE_OPERATOR_CONTENT],
        )

        created = client.post(
            f"/api/products/{product_id}/skus",
            headers=operator,
            json={"sku_name": "零价规格", "spec": "基础款", "price": 0},
        )
        assert created.status_code == 201
        assert created.json()["price"] == 0

        updated = client.put(
            f"/api/products/skus/{created.json()['id']}",
            headers=operator,
            json={"sku_name": "零价升级规格", "spec": "升级款", "price": 0},
        )
        assert updated.status_code == 200
        assert updated.json()["sku_name"] == "零价升级规格"
        assert updated.json()["spec"] == "升级款"
        assert updated.json()["price"] == 0

    def test_customer_service_cannot_create_or_update_sku_facts(self, client):
        product = client.post(
            "/api/products",
            json={
                "name": "SKU越权测试",
                "category": "测试",
                "skus": [{"sku_name": "原规格", "price": 10}],
            },
        )
        assert product.status_code == 201
        product_id = product.json()["id"]
        sku_id = product.json()["skus"][0]["id"]
        service = login_as(
            client,
            ROLE_CUSTOMER_SERVICE,
            TEST_PASSWORDS[ROLE_CUSTOMER_SERVICE],
        )

        create_response = client.post(
            f"/api/products/{product_id}/skus",
            headers=service,
            json={"sku_name": "越权新增", "price": 0},
        )
        update_response = client.put(
            f"/api/products/skus/{sku_id}",
            headers=service,
            json={"sku_name": "越权修改", "spec": "不应保存", "price": 0},
        )

        assert create_response.status_code == 403
        assert update_response.status_code == 403

        unchanged = client.get(f"/api/products/{product_id}")
        assert unchanged.status_code == 200
        assert len(unchanged.json()["skus"]) == 1
        assert unchanged.json()["skus"][0]["sku_name"] == "原规格"
        assert unchanged.json()["skus"][0]["price"] == 10


class TestInventoryUpdate:
    def test_update_inventory_first_time(self, client):
        """Update inventory for a SKU that has no inventory record yet."""
        resp = client.post("/api/products", json={
            "name": "库存首次", "category": "食品",
            "skus": [{"sku_name": "默认", "price": 20}]
        })
        sku_id = resp.json()["skus"][0]["id"]
        # SKU was created without inventory

        resp = client.put(f"/api/products/skus/{sku_id}/inventory", json={
            "stock_quantity": 200,
            "locked_quantity": 5,
            "safety_stock": 20,
        })
        assert resp.status_code == 200
        assert resp.json()["stock_quantity"] == 200

    def test_update_inventory_existing(self, client):
        """Update inventory that already has a record."""
        resp = client.post("/api/products", json={
            "name": "库存更新", "category": "美妆",
            "skus": [{
                "sku_name": "标准版", "price": 88,
                "inventory": {"stock_quantity": 100, "locked_quantity": 0, "safety_stock": 10}
            }]
        })
        sku_id = resp.json()["skus"][0]["id"]
        assert resp.json()["skus"][0]["inventory"]["stock_quantity"] == 100

        # Update
        resp = client.put(f"/api/products/skus/{sku_id}/inventory", json={
            "stock_quantity": 50,
            "locked_quantity": 3,
            "safety_stock": 5,
        })
        assert resp.status_code == 200
        assert resp.json()["stock_quantity"] == 50

    def test_update_inventory_sku_not_found(self, client):
        resp = client.put("/api/products/skus/99999/inventory", json={
            "stock_quantity": 100
        })
        assert resp.status_code == 404


class TestContentGeneration:
    def test_generate_content_template(self, client):
        resp = client.post("/api/products", json={
            "name": "防晒衣", "category": "服装", "brand": "优衣库",
            "selling_points": "UPF50+ 防晒，轻薄透气",
        })
        product_id = resp.json()["id"]
        assert client.put(f"/api/products/{product_id}", json={"status": "approved"}).status_code == 200

        package = client.post("/api/content/packages", json={"product_id": product_id, "payload": {}})
        assert package.status_code == 201
        resp = client.post(f"/api/content/packages/{package.json()['id']}/generate", json={"content_type": "title", "platform": "taobao"})
        assert resp.status_code == 200
        data = resp.json()["versions"][-1]
        assert data["task_status"] in {"completed", "no_key"}
        assert data["provider"]

    def test_generate_content_product_not_found(self, client):
        resp = client.post("/api/content/packages", json={"product_id": 99999, "payload": {}})
        assert resp.status_code == 404


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
