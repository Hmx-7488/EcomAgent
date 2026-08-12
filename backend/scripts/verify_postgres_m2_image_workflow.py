"""Run the M2 image approval/export workflow against a migrated PostgreSQL DB.

The local provider stub is installed in-process.  ``ECOMAGENT_TEST_MODE=1``
is required so no dotenv credentials or external provider can be used.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    os.environ.update(
        {
            "DATABASE_URL": args.database_url,
            "ECOMAGENT_TEST_MODE": "1",
            "GOOGLE_API_KEY": "",
            "LLM_API_KEY": "",
            "IMAGE_GEN_API_KEY": "",
        }
    )

    from fastapi.testclient import TestClient
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.main import app
    from app.models.user import User
    from app.services import image_service
    from scripts.image_fixture import png_bytes, verify_and_load_png

    suffix = hashlib.sha256(args.database_url.encode()).hexdigest()[:10]
    operator_name, admin_name, service_name = (f"m21_operator_{suffix}", f"m21_admin_{suffix}", f"m21_service_{suffix}")
    session = SessionLocal()
    try:
        for username, password, role in (
            (operator_name, "m21-operator-password", "operator_content"),
            (admin_name, "m21-admin-password", "admin"),
            (service_name, "m21-service-password", "customer_service"),
        ):
            user = session.query(User).filter(User.username == username).first()
            if user is None:
                session.add(User(username=username, password_hash=hash_password(password), role=role))
        session.commit()
    finally:
        session.close()

    original_provider = image_service.generate_image_with_provider
    image_service.generate_image_with_provider = lambda **_kwargs: {"images": [png_bytes(14, 12)]}
    try:
        with TestClient(app) as client:
            def login(username: str, password: str) -> dict[str, str]:
                response = client.post("/api/auth/login", json={"username": username, "password": password})
                assert response.status_code == 200, response.text
                return {"Authorization": f"Bearer {response.json()['access_token']}"}

            operator = login(operator_name, "m21-operator-password")
            admin = login(admin_name, "m21-admin-password")
            service = login(service_name, "m21-service-password")
            category = client.post(
                "/api/product-categories", headers=admin, json={"name": "Demo"}
            )
            assert category.status_code in (201, 409), category.text
            product = client.post(
                "/api/products",
                headers=operator,
                json={"name": "M2.1 PostgreSQL image workflow", "category": "Demo", "skus": [{"sku_name": "default", "price": 100}]},
            )
            assert product.status_code == 201, product.text
            product_id = product.json()["id"]
            assert client.put(f"/api/products/{product_id}", headers=operator, json={"status": "approved"}).status_code == 200
            reference = client.post(
                "/api/images/reference",
                headers=operator,
                data={"product_id": str(product_id)},
                files={"file": ("m21-reference.png", png_bytes(10, 8), "image/png")},
            )
            assert reference.status_code == 201, reference.text
            reference_name = reference.json()["url"].rsplit("/", 1)[-1]
            with open(os.path.join(image_service.UPLOAD_DIR, reference_name), "rb") as image_file:
                assert verify_and_load_png(image_file.read()) == (10, 8)
            task = client.post(
                "/api/images/tasks",
                headers=operator,
                json={"product_id": product_id, "style": "minimal", "reference_asset_id": reference.json()["id"]},
            )
            assert task.status_code == 202 and task.json()["status"] == "completed", task.text
            task_id = task.json()["task_id"]
            assert client.post(f"/api/images/tasks/{task_id}/export", headers=admin).status_code == 409
            assert client.post(f"/api/images/tasks/{task_id}/confirm", headers=operator, json={}).status_code == 200
            assert client.post(f"/api/images/tasks/{task_id}/export", headers=admin).status_code == 409
            assert client.post(f"/api/images/tasks/{task_id}/submit", headers=operator, json={}).status_code == 200
            assert client.post(f"/api/images/tasks/{task_id}/export", headers=service).status_code == 403
            assert client.post(f"/api/images/tasks/{task_id}/approve", headers=admin, json={}).status_code == 200
            exported = client.post(f"/api/images/tasks/{task_id}/export", headers=admin)
            assert exported.status_code == 200, exported.text
            assets = client.get(f"/api/images/assets/{product_id}", headers=operator)
            assert assets.status_code == 200, assets.text
            generated = next(item for item in assets.json()["items"] if item["id"] in exported.json()["asset_ids"])
            generated_name = generated["url"].rsplit("/", 1)[-1]
            with open(os.path.join(image_service.UPLOAD_DIR, generated_name), "rb") as image_file:
                assert verify_and_load_png(image_file.read()) == (14, 12)
            audit = client.get("/api/audit-events", headers=admin)
            assert audit.status_code == 200, audit.text
            actions = {item["action"] for item in audit.json()["items"] if item["target_id"] == task_id}
            required = {"image.created", "image.confirmed", "image.submitted", "image.approved", "image.exported"}
            assert required <= actions, required - actions
        print("postgres_m2_image_workflow=passed")
        return 0
    finally:
        image_service.generate_image_with_provider = original_provider


if __name__ == "__main__":
    raise SystemExit(main())
