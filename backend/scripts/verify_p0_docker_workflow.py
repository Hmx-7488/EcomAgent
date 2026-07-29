"""Verify the complete P0 workflow inside the backend Docker container.

This verifier deliberately runs the FastAPI app in-process while its SQLAlchemy
session points at the Docker PostgreSQL service. Provider boundaries are
replaced with local deterministic stubs before a request is made. It therefore
exercises the real API, authorization, persistence and audit code without
opening a production-only stub endpoint or making a network Provider call.

Run after ``alembic upgrade head``. Passwords are required inputs and have no
hard-coded defaults:

    python scripts/verify_p0_docker_workflow.py \
      --database-url "$DATABASE_URL" \
      --admin-password "$M4_ADMIN_PASSWORD" \
      --operator-password "$M4_OPERATOR_PASSWORD" \
      --service-password "$M4_SERVICE_PASSWORD"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

AUTH_PATH = "/api/auth/login"
MIN_PASSWORD_LENGTH = 12


def _required_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise argparse.ArgumentTypeError(
            f"acceptance passwords must contain at least {MIN_PASSWORD_LENGTH} characters"
        )
    return value


def _assert_status(response, expected: int, label: str) -> dict:
    assert response.status_code == expected, (
        f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
    )
    if not response.content:
        return {}
    return response.json()


def _clear_provider_environment(database_url: str) -> None:
    """Configure test isolation before importing any application module."""

    os.environ.update(
        {
            "DATABASE_URL": database_url,
            "ECOMAGENT_TEST_MODE": "1",
            "GOOGLE_API_KEY": "",
            "LLM_API_KEY": "",
            "LLM_API_BASE": "",
            "LLM_MODEL": "",
            "IMAGE_GEN_API_KEY": "",
            "IMAGE_GEN_API_BASE": "",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--admin-password", required=True, type=_required_password)
    parser.add_argument("--operator-password", required=True, type=_required_password)
    parser.add_argument("--service-password", required=True, type=_required_password)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    _clear_provider_environment(args.database_url)

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.main import app
    from app.models.user import User
    from app.services import content_service, image_service
    from app.services.customer_service import get_customer_reply_provider
    from scripts.image_fixture import png_bytes, verify_and_load_png

    assert not settings.llm_configured
    assert not settings.image_gen_configured

    users = (
        ("m4_acceptance_admin", args.admin_password, "admin"),
        ("m4_acceptance_operator", args.operator_password, "operator_content"),
        ("m4_acceptance_service", args.service_password, "customer_service"),
    )
    db = SessionLocal()
    try:
        # These dedicated acceptance identities are idempotently reconciled.
        # Production/demo identities are never modified by this verifier.
        for username, password, role in users:
            user = db.query(User).filter(User.username == username).first()
            if user is None:
                user = User(username=username)
                db.add(user)
            user.password_hash = hash_password(password)
            user.role = role
            user.is_active = True
        db.commit()
    finally:
        db.close()

    class OfflineCustomerDraftProvider:
        name = "m4_offline_customer_stub"

        def __init__(self) -> None:
            self.calls = 0

        def reply(self, _fact_text: str) -> str:
            raise AssertionError("low-risk replies must use the deterministic template")

        def draft(self, _question: str, _safe_fact_summary: str = "") -> str:
            self.calls += 1
            return "M4 offline internal review draft."

    customer_provider = OfflineCustomerDraftProvider()
    app.dependency_overrides[get_customer_reply_provider] = lambda: customer_provider
    original_content_provider = content_service.generate_package_with_provider
    original_image_provider = image_service.generate_image_with_provider
    content_service.generate_package_with_provider = (
        lambda **_kwargs: {
            "title": "M4 Demo content",
            "selling_points": ["approved facts only"],
        }
    )
    image_service.generate_image_with_provider = (
        lambda **_kwargs: [png_bytes(24, 18)]
    )

    run_id = uuid.uuid4().hex[:10]
    summary: dict[str, object] = {
        "run_id": run_id,
        "provider_mode": "offline_stubs",
        "database": "postgresql",
    }
    try:
        with TestClient(app) as client:

            def login(index: int) -> dict[str, str]:
                username, password, _role = users[index]
                payload = _assert_status(
                    client.post(
                        AUTH_PATH,
                        json={"username": username, "password": password},
                    ),
                    200,
                    f"login {username}",
                )
                return {"Authorization": f"Bearer {payload['access_token']}"}

            admin, operator, service = login(0), login(1), login(2)

            # Authentication and fixed-role access control.
            _assert_status(client.get("/api/products"), 401, "anonymous products")
            _assert_status(
                client.get("/api/service/conversations", headers=operator),
                403,
                "operator service queue",
            )
            _assert_status(
                client.get("/api/audit-events", headers=service),
                403,
                "service audit search",
            )

            # Product, SKU, all six cost facts and deterministic margin.
            product = _assert_status(
                client.post(
                    "/api/products",
                    headers=operator,
                    json={
                        "name": f"M4 acceptance product {run_id}",
                        "category": "Demo",
                        "brand": "EcomAgent",
                        "description": "Storage box for indoor use.",
                        "selling_points": "Reusable and easy to install.",
                        "parameters_json": json.dumps(
                            {
                                "material": "PP",
                                "size": "30 x 20 x 15 cm",
                                "capacity": "9 L",
                                "color": "white",
                                "package": "box and instruction card",
                                "usage": "snap the sides into place",
                                "scene": "desktop and wardrobe",
                            },
                            ensure_ascii=False,
                        ),
                        "shipping_rule_text": "No delivery-time promise.",
                        "skus": [
                            {
                                "sku_name": "standard-white",
                                "color": "white",
                                "size": "30 x 20 x 15 cm",
                                "spec": "9 L",
                                "price": 100,
                            }
                        ],
                    },
                ),
                201,
                "create product",
            )
            product_id = product["id"]
            sku_id = product["skus"][0]["id"]
            costs = {
                "purchase_cost": 40,
                "packaging_cost": 2,
                "shipping_subsidy": 3,
                "platform_fee": 5,
                "marketing_allocation": 4,
                "after_sales_loss": 1,
            }
            cost = _assert_status(
                client.post(
                    f"/api/skus/{sku_id}/costs", headers=operator, json=costs
                ),
                200,
                "write six costs",
            )
            assert cost["status"] == "ready" and not cost["completeness"]
            margin = _assert_status(
                client.get(f"/api/skus/{sku_id}/margin", headers=operator),
                200,
                "read margin",
            )
            assert margin["total_cost"] == 55
            assert margin["estimated_gross_profit"] == 45
            assert abs(margin["estimated_gross_margin_rate"] - 0.45) < 1e-9
            _assert_status(
                client.get(f"/api/skus/{sku_id}/margin", headers=service),
                403,
                "service margin isolation",
            )
            _assert_status(
                client.put(
                    f"/api/products/{product_id}",
                    headers=operator,
                    json={"status": "approved"},
                ),
                200,
                "approve product fact",
            )

            # Content generation, manual edit, approval and Markdown export.
            package = _assert_status(
                client.post(
                    "/api/content/packages",
                    headers=operator,
                    json={
                        "product_id": product_id,
                        "payload": {"title": "M4 initial Demo title"},
                    },
                ),
                201,
                "create content package",
            )
            package_id = package["id"]
            generated = _assert_status(
                client.post(
                    f"/api/content/packages/{package_id}/generate",
                    headers=operator,
                    json={"content_type": "title", "platform": "general"},
                ),
                200,
                "generate content with stub",
            )
            assert generated["versions"][-1]["task_status"] == "completed"
            edited_payload = {
                "title": "M4 approved Demo title",
                "selling_points": "Reusable PP material",
                "detail": "Fact-based product detail.",
                "parameters": "30 x 20 x 15 cm; 9 L",
                "faq": [{"q": "Material?", "a": "PP"}],
                "sales_script": "Describe only approved product facts.",
                "promo_material": "Demo graphic-copy material.",
            }
            _assert_status(
                client.patch(
                    f"/api/content/packages/{package_id}",
                    headers=operator,
                    json={"payload": edited_payload},
                ),
                200,
                "edit content package",
            )
            _assert_status(
                client.post(
                    f"/api/content/packages/{package_id}/submit",
                    headers=operator,
                ),
                200,
                "submit content",
            )
            _assert_status(
                client.post(
                    f"/api/content/packages/{package_id}/export", headers=admin
                ),
                409,
                "block unapproved content export",
            )
            _assert_status(
                client.post(
                    f"/api/content/packages/{package_id}/export", headers=service
                ),
                403,
                "block service content export",
            )
            _assert_status(
                client.post(
                    f"/api/content/packages/{package_id}/approve",
                    headers=admin,
                    json={},
                ),
                200,
                "approve content",
            )
            markdown = _assert_status(
                client.post(
                    f"/api/content/packages/{package_id}/export", headers=admin
                ),
                200,
                "export approved Markdown",
            )
            assert "M4 approved Demo title" in markdown["markdown"]

            # Reference image, local image stub, confirmation, approval and export.
            reference = _assert_status(
                client.post(
                    "/api/images/reference",
                    headers=operator,
                    data={"product_id": str(product_id)},
                    files={
                        "file": (
                            "m4-reference.png",
                            png_bytes(20, 16),
                            "image/png",
                        )
                    },
                ),
                201,
                "upload reference image",
            )
            reference_filename = reference["url"].rsplit("/", 1)[-1]
            with open(os.path.join(image_service.UPLOAD_DIR, reference_filename), "rb") as image_file:
                assert verify_and_load_png(image_file.read()) == (20, 16)
            summary["reference_image_pillow"] = "verify/load 20x16 PNG"
            task = _assert_status(
                client.post(
                    "/api/images/tasks",
                    headers=operator,
                    json={
                        "product_id": product_id,
                        "style": "minimal",
                        "reference_asset_id": reference["id"],
                    },
                ),
                202,
                "create image task",
            )
            task_id = task["task_id"]
            assert task["status"] == "completed"
            task_detail = _assert_status(
                client.get(f"/api/images/tasks/{task_id}", headers=operator),
                200,
                "read image task model",
            )
            assert task_detail["model_name"] == settings.image_gen_model
            _assert_status(
                client.post(f"/api/images/tasks/{task_id}/export", headers=admin),
                409,
                "block unconfirmed image export",
            )
            _assert_status(
                client.post(f"/api/images/tasks/{task_id}/confirm", headers=operator),
                200,
                "confirm generated image",
            )
            _assert_status(
                client.post(f"/api/images/tasks/{task_id}/submit", headers=operator),
                200,
                "submit image",
            )
            _assert_status(
                client.post(f"/api/images/tasks/{task_id}/export", headers=service),
                403,
                "block service image export",
            )
            _assert_status(
                client.post(
                    f"/api/images/tasks/{task_id}/approve",
                    headers=admin,
                    json={},
                ),
                200,
                "approve image",
            )
            image_export = _assert_status(
                client.post(f"/api/images/tasks/{task_id}/export", headers=admin),
                200,
                "export approved image",
            )
            assert image_export["asset_ids"]
            image_assets = _assert_status(
                client.get(f"/api/images/assets/{product_id}", headers=operator),
                200,
                "list validated image assets",
            )["items"]
            generated = next(
                item for item in image_assets
                if item["id"] in image_export["asset_ids"]
            )
            generated_filename = generated["url"].rsplit("/", 1)[-1]
            with open(os.path.join(image_service.UPLOAD_DIR, generated_filename), "rb") as image_file:
                assert verify_and_load_png(image_file.read()) == (24, 18)
            summary["generated_image_pillow"] = "verify/load 24x18 PNG"

            def create_customer_conversation() -> tuple[int, dict[str, str]]:
                created = _assert_status(
                    client.post(
                        "/api/customer/conversations",
                        json={"product_id": product_id},
                    ),
                    201,
                    "create anonymous conversation",
                )
                return created["id"], {
                    "X-Conversation-Token": created["access_token"]
                }

            # Low-risk deterministic fact answer.
            low_id, low_headers = create_customer_conversation()
            low = _assert_status(
                client.post(
                    f"/api/customer/conversations/{low_id}/messages",
                    headers=low_headers,
                    json={"content": "这个商品是什么材质？"},
                ),
                200,
                "low-risk fact",
            )
            assert low["decision"] == "auto_reply"
            assert low["reply"] and low["source_summary"]

            # Medium-risk draft is invisible until an authorized human sends it.
            medium_id, medium_headers = create_customer_conversation()
            medium = _assert_status(
                client.post(
                    f"/api/customer/conversations/{medium_id}/messages",
                    headers=medium_headers,
                    json={"content": "现在价格和优惠是多少？"},
                ),
                200,
                "medium-risk review",
            )
            assert medium["decision"] == "review_draft"
            assert medium["reply"] is None and medium["status"] == "waiting_review"
            medium_detail = _assert_status(
                client.get(
                    f"/api/service/conversations/{medium_id}", headers=service
                ),
                200,
                "service opens review",
            )
            assert medium_detail["pending_draft"]
            _assert_status(
                client.post(
                    f"/api/service/conversations/{medium_id}/send",
                    headers=service,
                    json={"content": "价格与优惠请以人工确认的信息为准。"},
                ),
                200,
                "service sends reviewed reply",
            )
            customer_after_review = _assert_status(
                client.get(
                    f"/api/customer/conversations/{medium_id}",
                    headers=medium_headers,
                ),
                200,
                "customer sees reviewed reply",
            )
            assert any(
                row["sender_type"] == "customer_service"
                for row in customer_after_review["messages"]
            )

            # High-risk transfer and administrator resolution.
            high_id, high_headers = create_customer_conversation()
            high = _assert_status(
                client.post(
                    f"/api/customer/conversations/{high_id}/messages",
                    headers=high_headers,
                    json={"content": "我要投诉质量问题并要求立即退款"},
                ),
                200,
                "high-risk transfer",
            )
            assert high["decision"] == "transfer"
            assert high["status"] == "transferred"
            assert high["notice"]["content"] == "已转人工，请等待客服处理"
            resolved = _assert_status(
                client.post(
                    f"/api/service/conversations/{high_id}/resolve", headers=admin
                ),
                200,
                "resolve transferred conversation",
            )
            assert resolved["status"] == "resolved"

            # Audit search and object-level evidence.
            audit = _assert_status(
                client.get("/api/audit-events", headers=admin),
                200,
                "audit search",
            )
            rows = audit["items"]

            def actions_for(target_type: str, target_id: int) -> set[str]:
                return {
                    row["action"]
                    for row in rows
                    if row["target_type"] == target_type
                    and row["target_id"] == target_id
                }

            content_actions = actions_for("content_package", package_id)
            assert {
                "content.created",
                "content.generated",
                "content.edited",
                "content.submitted",
                "content.approved",
                "content.exported",
            } <= content_actions
            image_actions = actions_for("image_task", task_id)
            assert {
                "image.created",
                "image.confirmed",
                "image.submitted",
                "image.approved",
                "image.exported",
            } <= image_actions
            low_actions = actions_for("conversation", low_id)
            assert {
                "conversation.created",
                "message.received",
                "risk.assessed",
                "fact.queried",
                "reply.auto_sent",
            } <= low_actions
            medium_actions = actions_for("conversation", medium_id)
            assert {
                "draft.generated",
                "draft.edited",
                "reply.agent_sent",
                "conversation.status_changed",
            } <= medium_actions
            high_actions = actions_for("conversation", high_id)
            assert {
                "conversation.transferred",
                "conversation.status_changed",
            } <= high_actions

            # C-F06 includes cost/margin object retrieval in the formal contract.
            sku_actions = actions_for("sku", sku_id)
            assert "cost.updated" in sku_actions, "missing cost.updated audit evidence"
            assert (
                "margin.calculated" in sku_actions
            ), "missing margin.calculated audit evidence"

            summary.update(
                {
                    "status": "passed",
                    "product_id": product_id,
                    "sku_id": sku_id,
                    "content_package_id": package_id,
                    "image_task_id": task_id,
                    "conversation_ids": [low_id, medium_id, high_id],
                    "customer_provider_calls": customer_provider.calls,
                    "audit_event_count": audit["total"],
                }
            )
    finally:
        app.dependency_overrides.pop(get_customer_reply_provider, None)
        content_service.generate_package_with_provider = original_content_provider
        image_service.generate_image_with_provider = original_image_provider

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("docker_p0_workflow=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
