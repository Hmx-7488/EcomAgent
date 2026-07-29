"""Prepare idempotent Qina-only service queues for local screenshot evidence."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.update(
    {
        "ECOMAGENT_TEST_MODE": "1",
        "GOOGLE_API_KEY": "",
        "LLM_API_KEY": "",
        "LLM_API_BASE": "",
        "LLM_MODEL": "",
        "IMAGE_GEN_API_KEY": "",
        "IMAGE_GEN_API_BASE": "",
    }
)

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.content import Conversation
from app.models.product import Product
from app.services.customer_service import get_customer_reply_provider


class OfflineDemoDraftProvider:
    name = "offline_demo_draft"

    def reply(self, _fact_text: str) -> str:
        raise AssertionError("low-risk facts must use the deterministic template")

    def draft(self, _question: str, _safe_fact_summary: str = "") -> str:
        return "价格与优惠信息需要人工核对，请客服确认当前有效信息后再回复顾客。"


def _create_conversation(client: TestClient, product_id: int) -> tuple[int, dict]:
    created = client.post(
        "/api/customer/conversations",
        json={"product_id": product_id},
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    return payload["id"], {"X-Conversation-Token": payload["access_token"]}


def _send(
    client: TestClient,
    conversation_id: int,
    headers: dict,
    content: str,
):
    response = client.post(
        f"/api/customer/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": content},
    )
    assert response.status_code == 200, response.text
    return response.json()


def main() -> int:
    session = SessionLocal()
    try:
        product = (
            session.query(Product)
            .filter(
                Product.brand == "栖纳家居",
                Product.status == "approved",
                Product.is_deleted.is_(False),
            )
            .order_by(Product.id)
            .first()
        )
        if product is None:
            raise SystemExit("Run init_demo.py before preparing evidence")
        existing = {
            row.status
            for row in session.query(Conversation)
            .filter(Conversation.product_id == product.id)
            .all()
            if row.status in {"waiting_review", "transferred"}
        }
        product_id = product.id
    finally:
        session.close()

    provider = OfflineDemoDraftProvider()
    app.dependency_overrides[get_customer_reply_provider] = lambda: provider
    created_statuses: list[str] = []
    try:
        with TestClient(app) as client:
            if "waiting_review" not in existing:
                conversation_id, headers = _create_conversation(client, product_id)
                low = _send(
                    client,
                    conversation_id,
                    headers,
                    "这款商品是什么材质？",
                )
                assert low["decision"] == "auto_reply"
                medium = _send(
                    client,
                    conversation_id,
                    headers,
                    "现在价格和优惠是多少？",
                )
                assert medium["status"] == "waiting_review"
                created_statuses.append("waiting_review")
            if "transferred" not in existing:
                conversation_id, headers = _create_conversation(client, product_id)
                high = _send(
                    client,
                    conversation_id,
                    headers,
                    "商品有严重质量问题，我要投诉并要求人工处理。",
                )
                assert high["status"] == "transferred"
                created_statuses.append("transferred")
    finally:
        app.dependency_overrides.pop(get_customer_reply_provider, None)

    print(
        json.dumps(
            {
                "status": "ready",
                "product_scope": "栖纳家居",
                "created_queue_states": created_statuses,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
