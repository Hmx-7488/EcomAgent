"""Tests for product CRUD API."""


class TestProductAPI:
    """Integration tests for product endpoints."""

    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "EcomAgent"

    def test_create_product(self, client):
        payload = {
            "name": "测试商品",
            "category": "服装",
            "brand": "测试品牌",
            "description": "这是一款测试商品",
            "selling_points": "品质优良，性价比高",
            "skus": [
                {
                    "sku_name": "白色-M",
                    "color": "白色",
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
        response = client.post("/api/products", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "测试商品"
        assert data["category"] == "服装"
        assert len(data["skus"]) == 1
        assert data["skus"][0]["sku_name"] == "白色-M"
        assert data["skus"][0]["price"] == 99.0

    def test_list_products(self, client):
        # Create a product first
        client.post(
            "/api/products",
            json={
                "name": "列表测试商品",
                "category": "数码",
                "skus": [{"sku_name": "默认", "price": 199.0}],
            },
        )
        response = client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    def test_get_product_not_found(self, client):
        response = client.get("/api/products/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Product not found"

    def test_soft_delete_product(self, client):
        # Create
        resp = client.post(
            "/api/products",
            json={
                "name": "待删除商品",
                "category": "食品",
                "skus": [{"sku_name": "默认", "price": 10.0}],
            },
        )
        product_id = resp.json()["id"]

        # Delete
        resp = client.delete(f"/api/products/{product_id}")
        assert resp.status_code == 204

        # Verify soft-deleted — should not appear in list
        resp = client.get("/api/products")
        items = resp.json()["items"]
        deleted_ids = [p["id"] for p in items]
        assert product_id not in deleted_ids

    def test_update_product(self, client):
        # Create
        resp = client.post(
            "/api/products",
            json={
                "name": "更新前",
                "category": "图书",
                "skus": [{"sku_name": "默认", "price": 50.0}],
            },
        )
        product_id = resp.json()["id"]

        # Update
        resp = client.put(
            f"/api/products/{product_id}",
            json={"name": "更新后", "selling_points": "全新卖点"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "更新后"
        assert data["selling_points"] == "全新卖点"


class TestContentAPI:
    """Tests for content generation endpoints."""

    def test_generate_content(self, client):
        # Create a product first
        resp = client.post(
            "/api/products",
            json={
                "name": "内容测试商品",
                "category": "美妆",
                "selling_points": "天然成分，温和不刺激",
                "skus": [{"sku_name": "默认", "price": 128.0}],
            },
        )
        product_id = resp.json()["id"]

        # Generate content (template fallback since LLM isn't configured in tests)
        resp = client.post(
            "/api/content/generate",
            json={
                "product_id": product_id,
                "content_type": "title",
                "platform": "taobao",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_id"] == product_id
        assert data["content_type"] == "title"
        assert data["content_json"] is not None

    def test_generate_content_product_not_found(self, client):
        resp = client.post(
            "/api/content/generate",
            json={"product_id": 99999, "content_type": "title", "platform": "general"},
        )
        assert resp.status_code == 404
