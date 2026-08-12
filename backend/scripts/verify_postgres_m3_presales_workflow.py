"""Run the offline P0 M3 presales workflow against migrated PostgreSQL."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path: sys.path.insert(0, str(BACKEND_ROOT))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    os.environ.update({"DATABASE_URL": args.database_url, "ECOMAGENT_TEST_MODE": "1",
        "GOOGLE_API_KEY": "", "LLM_API_KEY": "", "IMAGE_GEN_API_KEY": ""})
    from fastapi.testclient import TestClient
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.main import app
    from app.models.user import User
    from app.services.customer_service import get_customer_reply_provider

    class OfflineDraftProvider:
        name = "postgres_offline_stub"

        def __init__(self):
            self.calls = 0

        def reply(self, fact_text):
            raise AssertionError("Low-risk replies must not call a Provider")

        def draft(self, _question, _safe_fact_summary=""):
            self.calls += 1
            return "Internal PostgreSQL review draft."

    provider = OfflineDraftProvider()
    app.dependency_overrides[get_customer_reply_provider] = lambda: provider

    suffix = hashlib.sha256(args.database_url.encode()).hexdigest()[:10]
    users = ((f"m3_operator_{suffix}", "m3-operator-password", "operator_content"),
        (f"m3_admin_{suffix}", "m3-admin-password", "admin"),
        (f"m3_service_{suffix}", "m3-service-password", "customer_service"))
    db = SessionLocal()
    try:
        for username, password, role in users:
            if not db.query(User).filter(User.username == username).first():
                db.add(User(username=username, password_hash=hash_password(password), role=role))
        db.commit()
    finally: db.close()

    with TestClient(app) as client:
        def login(index):
            username, password, _ = users[index]
            response = client.post("/api/auth/login", json={"username": username, "password": password})
            assert response.status_code == 200, response.text
            return {"Authorization": f"Bearer {response.json()['access_token']}"}
        operator, admin, service = login(0), login(1), login(2)
        category = client.post(
            "/api/product-categories", headers=admin, json={"name": "Demo"}
        )
        assert category.status_code in (201, 409), category.text
        product = client.post("/api/products", headers=operator, json={"name": f"M3 PostgreSQL {uuid.uuid4().hex[:8]}",
            "category": "Demo", "description": "Storage item for desktop use.",
            "parameters_json": json.dumps({"material": "PP", "color": "white", "package": "one item"}),
            "skus": [{"sku_name": "standard", "price": 100}]})
        assert product.status_code == 201, product.text
        product_id = product.json()["id"]
        assert client.put(f"/api/products/{product_id}", headers=operator, json={"status": "approved"}).status_code == 200
        created = client.post("/api/customer/conversations", json={"product_id": product_id})
        assert created.status_code == 201, created.text
        conversation_id, token = created.json()["id"], created.json()["access_token"]
        customer_headers = {"X-Conversation-Token": token}
        other = client.post("/api/customer/conversations", json={"product_id": product_id})
        assert other.status_code == 201
        assert client.get(f"/api/customer/conversations/{conversation_id}",
            headers={"X-Conversation-Token": other.json()["access_token"]}).status_code == 403

        low = client.post(f"/api/customer/conversations/{conversation_id}/messages", headers=customer_headers,
            json={"content": "\u8fd9\u4e2a\u5546\u54c1\u662f\u4ec0\u4e48\u6750\u8d28\uff1f"})
        assert low.status_code == 200 and low.json()["decision"] == "auto_reply", low.text
        assert low.json()["source_summary"] and low.json()["reply"]
        medium = client.post(f"/api/customer/conversations/{conversation_id}/messages", headers=customer_headers,
            json={"content": "\u73b0\u5728\u591a\u5c11\u94b1\uff1f"})
        assert medium.status_code == 200 and medium.json()["decision"] == "review_draft", medium.text
        assert medium.json()["reply"] is None and medium.json()["status"] == "waiting_review"
        assert client.get("/api/service/conversations", headers=operator).status_code == 403
        detail = client.get(f"/api/service/conversations/{conversation_id}", headers=service)
        assert detail.status_code == 200 and detail.json()["pending_draft"], detail.text
        draft_id = detail.json()["pending_draft"]["id"]
        calls_before_supplement = provider.calls
        supplement = client.post(
            f"/api/customer/conversations/{conversation_id}/messages",
            headers=customer_headers,
            json={"content": "\u8865\u5145\uff1a\u6750\u8d28\u662f\u4ec0\u4e48\uff1f"},
        )
        assert supplement.status_code == 200 and supplement.json()["status"] == "waiting_review"
        detail_after_supplement = client.get(
            f"/api/service/conversations/{conversation_id}", headers=service
        ).json()
        assert provider.calls == calls_before_supplement
        assert detail_after_supplement["pending_draft"]["id"] == draft_id
        sent = client.post(f"/api/service/conversations/{conversation_id}/send", headers=service,
            json={"content": "Reviewed safe reply."})
        assert sent.status_code == 200 and sent.json()["status"] == "open", sent.text
        high = client.post(f"/api/customer/conversations/{conversation_id}/messages", headers=customer_headers,
            json={"content": "\u6211\u8981\u6295\u8bc9\u8d28\u91cf\u95ee\u9898"})
        assert high.status_code == 200 and high.json()["decision"] == "transfer", high.text
        assert high.json()["notice"]["content"] == "\u5df2\u8f6c\u4eba\u5de5\uff0c\u8bf7\u7b49\u5f85\u5ba2\u670d\u5904\u7406"
        transferred_detail = client.get(
            f"/api/service/conversations/{conversation_id}", headers=service
        ).json()
        transfer_notice_count = sum(
            message["message_type"] == "transfer_notice"
            for message in transferred_detail["messages"]
        )
        calls_before_transfer_supplement = provider.calls
        transfer_supplement = client.post(
            f"/api/customer/conversations/{conversation_id}/messages",
            headers=customer_headers,
            json={"content": "\u8865\u5145\uff1a\u6750\u8d28\u662f\u4ec0\u4e48\uff1f"},
        )
        assert (
            transfer_supplement.status_code == 200
            and transfer_supplement.json()["status"] == "transferred"
        )
        transferred_after = client.get(
            f"/api/service/conversations/{conversation_id}", headers=service
        ).json()
        assert provider.calls == calls_before_transfer_supplement
        assert sum(
            message["message_type"] == "transfer_notice"
            for message in transferred_after["messages"]
        ) == transfer_notice_count
        resolved = client.post(f"/api/service/conversations/{conversation_id}/resolve", headers=admin)
        assert resolved.status_code == 200 and resolved.json()["status"] == "resolved", resolved.text
        audit = client.get("/api/audit-events", headers=admin)
        assert audit.status_code == 200, audit.text
        actions = {row["action"] for row in audit.json()["items"]
            if row["target_type"] == "conversation" and row["target_id"] == conversation_id}
        required = {"conversation.created", "risk.assessed", "fact.queried", "reply.auto_sent",
            "draft.generated", "reply.agent_sent", "conversation.transferred", "conversation.status_changed"}
        assert required <= actions, required - actions
    app.dependency_overrides.pop(get_customer_reply_provider, None)
    print("postgres_m3_presales_workflow=passed")
    return 0

if __name__ == "__main__": raise SystemExit(main())
