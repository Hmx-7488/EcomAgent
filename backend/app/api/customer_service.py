"""P0 M3 public presales and protected service-workbench APIs."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import require_roles
from ..models.content import Conversation, ConversationDecision, ConversationFactSource, ConversationMessage
from ..models.product import Product
from ..models.user import User
from ..schemas.customer_service import (ConversationCreate, ConversationCreated,
    CustomerConversationRead, CustomerMessageCreate, CustomerMessageResult,
    CustomerProductListResponse, ServiceSendRequest, ServiceTransferRequest)
from ..services.customer_service import (CustomerReplyProvider, authorize_customer_conversation,
    create_customer_conversation, customer_messages, get_customer_reply_provider,
    process_customer_message, service_resolve, service_send, service_transfer)

customer_router = APIRouter(prefix="/api/customer", tags=["customer-presales"])
service_router = APIRouter(prefix="/api/service/conversations", tags=["service-workbench"])

def _error(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message})

def _product_ref(product: Product) -> dict:
    return {"id": product.id, "name": product.name}

def _conversation(db: Session, conversation_id: int) -> Conversation:
    item = db.get(Conversation, conversation_id)
    if not item or item.product_id is None: _error(404, "not_found", "Conversation not found")
    return item

def _customer_auth(db: Session, conversation_id: int, token: Optional[str]):
    if not token: _error(401, "authentication_required", "Conversation token required")
    try: return authorize_customer_conversation(db, conversation_id, token)
    except PermissionError: _error(403, "permission_denied", "Conversation access denied")

def _public_message(message: Optional[ConversationMessage]):
    if not message: return None
    return {"id": message.id, "sender_type": message.sender_type,
        "content": message.content, "created_at": message.created_at}

@customer_router.get("/products", response_model=CustomerProductListResponse)
def list_customer_products(db: Session = Depends(get_db)):
    rows = db.query(Product).filter(Product.status == "approved", Product.is_deleted == False).order_by(Product.id).all()  # noqa: E712
    return {"items": [{"id": row.id, "name": row.name, "category": row.category,
        "brand": row.brand, "summary": row.description, "status": "approved"} for row in rows], "total": len(rows)}

@customer_router.post("/conversations", response_model=ConversationCreated, status_code=201)
def create_conversation(data: ConversationCreate, db: Session = Depends(get_db)):
    try: item, token = create_customer_conversation(db, data.product_id)
    except LookupError: _error(404, "not_found", "Approved product not found")
    product = db.get(Product, item.product_id)
    return {"id": item.id, "status": item.status, "product": _product_ref(product),
        "access_token": token, "created_at": item.created_at, "reason_code": None}

@customer_router.get("/conversations/{conversation_id}", response_model=CustomerConversationRead)
def get_customer_conversation(conversation_id: int,
        token: Optional[str] = Header(None, alias="X-Conversation-Token"), db: Session = Depends(get_db)):
    item = _customer_auth(db, conversation_id, token); product = db.get(Product, item.product_id)
    latest = db.query(ConversationDecision).filter(ConversationDecision.conversation_id == item.id).order_by(
        ConversationDecision.id.desc()).first()
    return {"id": item.id, "status": item.status, "product": _product_ref(product),
        "reason_code": latest.reason_code if latest else None, "messages": customer_messages(db, item),
        "created_at": item.created_at, "updated_at": item.updated_at}

@customer_router.post("/conversations/{conversation_id}/messages", response_model=CustomerMessageResult)
def send_customer_message(conversation_id: int, data: CustomerMessageCreate,
        token: Optional[str] = Header(None, alias="X-Conversation-Token"), db: Session = Depends(get_db),
        provider: CustomerReplyProvider = Depends(get_customer_reply_provider)):
    item = _customer_auth(db, conversation_id, token)
    try: decision = process_customer_message(db, item, data.content, provider)
    except RuntimeError as exc:
        if str(exc) == "conversation_resolved": _error(409, "conversation_resolved", "Conversation is resolved")
        raise
    customer = db.get(ConversationMessage, decision.customer_message_id)
    following = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == item.id,
        ConversationMessage.id > customer.id, ConversationMessage.visible_to_customer == True).order_by(ConversationMessage.id).all()  # noqa: E712
    reply = next((row for row in following if row.message_type in {"auto_reply", "staff_reply"}), None)
    notice = next((row for row in following if row.message_type in {"waiting_notice", "transfer_notice"}), None)
    return {"conversation_id": item.id, "status": item.status, "risk_level": decision.risk_level,
        "decision": decision.decision, "reason_code": decision.reason_code,
        "customer_message": _public_message(customer), "reply": _public_message(reply),
        "notice": _public_message(notice), "source_summary": json.loads(decision.source_summary)}

def _service_summary(db: Session, item: Conversation) -> dict:
    product = db.get(Product, item.product_id)
    latest = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == item.id,
        ConversationMessage.message_type == "customer").order_by(ConversationMessage.id.desc()).first()
    return {"id": item.id, "product": _product_ref(product), "status": item.status,
        "last_risk_level": item.last_risk_level, "transfer_reason": item.transfer_reason,
        "last_customer_message": latest.content if latest else None, "last_customer_message_detail": _public_message(latest), "created_at": item.created_at, "updated_at": item.updated_at}

def _service_detail(db: Session, item: Conversation) -> dict:
    result = _service_summary(db, item)
    messages = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == item.id).order_by(ConversationMessage.id).all()
    decisions = db.query(ConversationDecision).filter(ConversationDecision.conversation_id == item.id).order_by(ConversationDecision.id).all()
    decision_rows = []
    all_sources = []
    for decision in decisions:
        sources = db.query(ConversationFactSource).filter(ConversationFactSource.decision_id == decision.id).all()
        safe_sources = [{"source_type": source.source_type, "source_object_id": source.source_object_id,
            "source_version": source.source_version, "field_summary": source.field_summary, "data_time": source.data_time}
            for source in sources]
        all_sources.extend(safe_sources)
        decision_rows.append({"id": decision.id, "customer_message_id": decision.customer_message_id,
            "risk_level": decision.risk_level, "decision": decision.decision, "reason_code": decision.reason_code,
            "source_summary": json.loads(decision.source_summary), "provider_status": decision.provider_status,
            "created_at": decision.created_at, "fact_sources": safe_sources})
    pending = next((row for row in reversed(messages) if row.message_type == "review_draft"), None) if item.status == "waiting_review" else None
    result.update({"messages": [{"id": row.id, "sender_type": row.sender_type,
        "message_type": row.message_type, "content": row.content,
        "visibility": "customer" if row.visible_to_customer else "internal",
        "visible_to_customer": row.visible_to_customer, "actor_id": row.actor_id,
        "created_at": row.created_at} for row in messages],
        "decisions": decision_rows, "fact_sources": all_sources, "pending_draft": _public_message(pending)})
    return result
@service_router.get("")
def list_service_conversations(status: Optional[str] = Query(None), db: Session = Depends(get_db),
        _: User = Depends(require_roles("customer_service", "admin"))):
    allowed = {"waiting_review", "transferred"}
    if status and status not in allowed: _error(422, "validation_error", "Queue status must be waiting_review or transferred")
    query = db.query(Conversation).filter(Conversation.product_id.isnot(None))
    query = query.filter(Conversation.status == status) if status else query.filter(Conversation.status.in_(allowed))
    rows = query.order_by(Conversation.updated_at.desc()).all()
    return {"items": [_service_summary(db, row) for row in rows], "total": len(rows)}

@service_router.get("/{conversation_id}")
def get_service_conversation(conversation_id: int, db: Session = Depends(get_db),
        _: User = Depends(require_roles("customer_service", "admin"))):
    return _service_detail(db, _conversation(db, conversation_id))

@service_router.post("/{conversation_id}/send")
def send_service_reply(conversation_id: int, data: ServiceSendRequest, db: Session = Depends(get_db),
        actor: User = Depends(require_roles("customer_service", "admin"))):
    try: item = service_send(db, _conversation(db, conversation_id), actor, data.content)
    except RuntimeError as exc: _error(409, str(exc), "Conversation is not ready for reviewed send")
    return _service_detail(db, item)

@service_router.post("/{conversation_id}/transfer")
def transfer_service_conversation(conversation_id: int, data: ServiceTransferRequest,
        db: Session = Depends(get_db), actor: User = Depends(require_roles("customer_service", "admin"))):
    try: item = service_transfer(db, _conversation(db, conversation_id), actor, data.reason)
    except RuntimeError as exc: _error(409, str(exc), "Conversation cannot be transferred")
    return _service_detail(db, item)

@service_router.post("/{conversation_id}/resolve")
def resolve_service_conversation(conversation_id: int, db: Session = Depends(get_db),
        actor: User = Depends(require_roles("customer_service", "admin"))):
    return _service_detail(db, service_resolve(db, _conversation(db, conversation_id), actor))
