"""Generated content and conversation models."""

import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class GeneratedContent(Base):
    __tablename__ = "generated_contents"
    __table_args__ = (Index("ix_generated_contents_product_id", "product_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[Optional[str]] = mapped_column(String(64))
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32))
    content_json: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    product: Mapped["Product"] = relationship("Product", back_populates="generated_contents")


class ContentPackage(Base):
    """A reviewable P0 content and promotion-material package."""

    __tablename__ = "content_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    source_fact_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ContentVersion(Base):
    """Append-only content package payload; approved history is never overwritten."""

    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version_no", name="uq_content_package_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_packages.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="template")
    model_name: Mapped[Optional[str]] = mapped_column(String(128))
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    error_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    before_json: Mapped[Optional[str]] = mapped_column(Text)
    after_json: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_product_id", "product_id"),
        Index("ix_conversations_status", "status"),
        UniqueConstraint("token_digest", name="uq_conversations_token_digest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("products.id"))
    token_digest: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    last_risk_level: Mapped[Optional[str]] = mapped_column(String(16))
    transfer_reason: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("ix_conversation_messages_conversation_id", "conversation_id"),
        Index("ix_conversation_messages_actor_id", "actor_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visible_to_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class ConversationDecision(Base):
    __tablename__ = "conversation_decisions"
    __table_args__ = (
        UniqueConstraint("customer_message_id", name="uq_conversation_decision_message"),
        Index("ix_conversation_decisions_conversation_id", "conversation_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), nullable=False)
    customer_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversation_messages.id"), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_summary: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provider_status: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class ConversationFactSource(Base):
    __tablename__ = "conversation_fact_sources"
    __table_args__ = (Index("ix_conversation_fact_sources_decision_id", "decision_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversation_decisions.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    field_summary: Mapped[str] = mapped_column(Text, nullable=False)
    data_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class ToolCallLog(Base):
    __tablename__ = "tool_call_logs"
    __table_args__ = (Index("ix_tool_call_logs_conversation_id", "conversation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("conversations.id")
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments_json: Mapped[Optional[str]] = mapped_column(Text)
    result_summary: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="success")  # success/error
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
