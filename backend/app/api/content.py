"""Controlled P0 content package APIs. No publishing or platform action exists here."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import require_roles
from ..models.content import AuditEvent, ContentPackage
from ..models.user import User
from ..schemas.content import (AuditEventListResponse, ContentGenerateRequest, ContentPackageCreate,
    ContentPackageListResponse, ContentPackageRead, ContentPackageUpdate, ContentTransitionRequest, MarkdownExportRead)
from ..services.content_service import (create_package, edit_package, export_package, generate_package,
    package_read, transition_package)

router = APIRouter(prefix="/api/content", tags=["content"])

def _package(db: Session, package_id: int) -> ContentPackage:
    item = db.get(ContentPackage, package_id)
    if not item: raise HTTPException(404, detail={"code":"not_found","message":"Content package not found"})
    return item

def _service_error(exc: Exception):
    codes = {"product_not_found": (404, "not_found", "Product not found"),
             "approved_product_required": (409, "conflict", "Only approved product facts can be used"),
             "approved_version_immutable": (409, "approved_version_immutable", "Approved content history is immutable"),
             "illegal_status_transition": (409, "illegal_status_transition", "Illegal approval status transition"),
             "rejection_reason_required": (422, "validation_error", "Rejection reason is required"),
             "approval_required": (409, "approval_required", "Approved content is required for export")}
    status, code, message = codes.get(str(exc), (400, "content_error", "Content operation failed"))
    raise HTTPException(status, detail={"code":code,"message":message})

@router.get("/packages", response_model=ContentPackageListResponse)
def list_packages(db: Session=Depends(get_db), _: User=Depends(require_roles("admin", "operator_content"))):
    records = db.query(ContentPackage).order_by(ContentPackage.updated_at.desc()).all()
    return {"items":[package_read(db, item) for item in records], "total":len(records)}

@router.post("/packages", response_model=ContentPackageRead, status_code=201)
def create(data: ContentPackageCreate, db: Session=Depends(get_db), user: User=Depends(require_roles("admin", "operator_content"))):
    try: return package_read(db, create_package(db, user, data.product_id, data.payload))
    except (ValueError, RuntimeError, LookupError) as exc: _service_error(exc)

@router.get("/packages/{package_id}", response_model=ContentPackageRead)
def get(package_id: int, db: Session=Depends(get_db), _: User=Depends(require_roles("admin", "operator_content"))): return package_read(db, _package(db, package_id))

@router.patch("/packages/{package_id}", response_model=ContentPackageRead)
def edit(package_id: int, data: ContentPackageUpdate, db: Session=Depends(get_db), user: User=Depends(require_roles("admin", "operator_content"))):
    try: return package_read(db, edit_package(db, user, _package(db, package_id), data.payload))
    except (ValueError, RuntimeError) as exc: _service_error(exc)

@router.post("/packages/{package_id}/generate", response_model=ContentPackageRead)
def generate(package_id: int, data: ContentGenerateRequest, db: Session=Depends(get_db), user: User=Depends(require_roles("admin", "operator_content"))):
    try: return package_read(db, generate_package(db, user, _package(db, package_id), data.content_type, data.platform, data.style_hint))
    except (ValueError, RuntimeError) as exc: _service_error(exc)

@router.post("/packages/{package_id}/submit", response_model=ContentPackageRead)
def submit(package_id: int, db: Session=Depends(get_db), user: User=Depends(require_roles("admin", "operator_content"))):
    try: return package_read(db, transition_package(db, user, _package(db, package_id), "submit"))
    except (ValueError, RuntimeError) as exc: _service_error(exc)

@router.post("/packages/{package_id}/approve", response_model=ContentPackageRead)
def approve(package_id: int, data: ContentTransitionRequest, db: Session=Depends(get_db), user: User=Depends(require_roles("admin"))):
    try: return package_read(db, transition_package(db, user, _package(db, package_id), "approve", data.reason))
    except (ValueError, RuntimeError) as exc: _service_error(exc)

@router.post("/packages/{package_id}/reject", response_model=ContentPackageRead)
def reject(package_id: int, data: ContentTransitionRequest, db: Session=Depends(get_db), user: User=Depends(require_roles("admin"))):
    try: return package_read(db, transition_package(db, user, _package(db, package_id), "reject", data.reason))
    except (ValueError, RuntimeError) as exc: _service_error(exc)

@router.post("/packages/{package_id}/export", response_model=MarkdownExportRead)
def export(package_id: int, db: Session=Depends(get_db), user: User=Depends(require_roles("admin"))):
    try: return export_package(db, user, _package(db, package_id))
    except (ValueError, RuntimeError) as exc: _service_error(exc)

router_audit = APIRouter(prefix="/api/audit-events", tags=["audit"])
@router_audit.get("", response_model=AuditEventListResponse)
def audit_events(
    target_type: Optional[str] = Query(default=None, max_length=32),
    target_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    query = db.query(AuditEvent)
    if target_type is not None:
        query = query.filter(AuditEvent.target_type == target_type)
    if target_id is not None:
        query = query.filter(AuditEvent.target_id == target_id)
    records = query.order_by(AuditEvent.created_at.desc()).all()
    return {"items": records, "total": len(records)}
