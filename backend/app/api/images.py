"""P0 controlled image task APIs; they never publish to external platforms."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import require_roles
from ..models.asset import Asset, ImageGenerationTask
from ..models.product import Product
from ..models.user import User
from ..schemas.asset import AssetListResponse, AssetRead, ImageExportRead, ImageGenerateRequest, ImageTaskCreateResponse, ImageTaskRead, ImageTransitionRequest
from ..services import image_service
from ..services.content_service import _audit

router = APIRouter(prefix="/api/images", tags=["images"])

def _task(db: Session, task_id: int) -> ImageGenerationTask:
    item = db.get(ImageGenerationTask, task_id)
    if not item: raise HTTPException(404, detail={"code":"not_found","message":"Image task not found"})
    return item
def _error(exc: Exception):
    mapping = {"approved_product_required":(409,"approved_product_required","Only approved product facts can be used"),
               "retry_not_available":(409,"retry_not_available","Task is not in a retryable state"),
               "completed_image_required":(409,"completed_image_required","Completed image is required for confirmation"),
               "illegal_status_transition":(409,"illegal_status_transition","Illegal approval status transition"),
               "rejection_reason_required":(422,"validation_error","Rejection reason is required"),
               "approval_required":(409,"approval_required","Approved confirmed image is required for export")}
    status, code, message = mapping.get(str(exc),(400,"image_error","Image operation failed"))
    raise HTTPException(status, detail={"code":code,"message":message})

@router.post("/reference", response_model=AssetRead, status_code=201)
def reference(product_id: int=Form(...), file: UploadFile=File(...), db: Session=Depends(get_db), user: User=Depends(require_roles("admin","operator_content"))):
    product = db.get(Product, product_id)
    if not product or product.status != "approved": raise HTTPException(409, detail={"code":"approved_product_required","message":"Only approved product facts can be used"})
    if not file.filename:
        raise HTTPException(422, detail={"code":"validation_error","message":"An image reference is required"})
    file_bytes = file.file.read(image_service.MAX_FILE_SIZE + 1)
    try:
        asset = image_service.save_upload(
            db, product_id, file_bytes, file.filename, "reference", file.content_type
        )
    except ValueError as exc: raise HTTPException(422, detail={"code":"validation_error","message":str(exc)})
    _audit(db, user, "image.reference_uploaded", "media_asset", asset.id, summary="Uploaded reference image"); db.commit(); return asset

@router.get("/reference", response_model=AssetListResponse)
def list_reference(product_id: int, db: Session=Depends(get_db), _: User=Depends(require_roles("admin","operator_content"))):
    items = db.query(Asset).filter(Asset.product_id==product_id, Asset.asset_type=="reference").all(); return {"items":items,"total":len(items)}

@router.post("/tasks", response_model=ImageTaskCreateResponse, status_code=202)
def create_task(data: ImageGenerateRequest, db: Session=Depends(get_db), user: User=Depends(require_roles("admin","operator_content"))):
    product = db.get(Product, data.product_id)
    if not product or product.status != "approved": raise HTTPException(409, detail={"code":"approved_product_required","message":"Only approved product facts can be used"})
    ref = db.get(Asset, data.reference_asset_id) if data.reference_asset_id else db.query(Asset).filter(Asset.product_id==data.product_id, Asset.asset_type=="reference").order_by(Asset.created_at.desc()).first()
    if not ref or ref.product_id != data.product_id or ref.asset_type != "reference": raise HTTPException(422, detail={"code":"validation_error","message":"A validated reference image is required"})
    task = image_service.create_generation_task(db, data.product_id, ref.id, data.style)
    _audit(db, user, "image.created", "image_task", task.id, after={"status":"pending"}, summary="Created image generation task"); db.commit()
    # P0 exposes state through a task resource, but this local deployment has
    # no worker queue. Process once synchronously; adapters remain injectable.
    task = image_service.process_generation_task(db, task.id)
    return {"task_id":task.id,"status":task.status}

@router.get("/tasks", response_model=list[ImageTaskRead])
def list_tasks(product_id: int|None=None, db: Session=Depends(get_db), _: User=Depends(require_roles("admin","operator_content"))):
    q=db.query(ImageGenerationTask); return q.filter(ImageGenerationTask.product_id==product_id).all() if product_id else q.all()
@router.get("/tasks/{task_id}", response_model=ImageTaskRead)
def get_task(task_id: int, db: Session=Depends(get_db), _: User=Depends(require_roles("admin","operator_content"))): return _task(db, task_id)

@router.post("/tasks/{task_id}/retry", response_model=ImageTaskRead)
def retry(task_id:int, db:Session=Depends(get_db), user:User=Depends(require_roles("admin","operator_content"))):
    try:return image_service.retry_task(db,user,_task(db,task_id))
    except (ValueError,RuntimeError) as exc:_error(exc)
@router.post("/tasks/{task_id}/confirm", response_model=ImageTaskRead)
def confirm(task_id:int, db:Session=Depends(get_db), user:User=Depends(require_roles("admin","operator_content"))):
    try:return image_service.confirm_task(db,user,_task(db,task_id))
    except (ValueError,RuntimeError) as exc:_error(exc)
@router.post("/tasks/{task_id}/submit", response_model=ImageTaskRead)
def submit(task_id:int, db:Session=Depends(get_db), user:User=Depends(require_roles("admin","operator_content"))):
    try:return image_service.transition_task(db,user,_task(db,task_id),"submit")
    except (ValueError,RuntimeError) as exc:_error(exc)
@router.post("/tasks/{task_id}/approve", response_model=ImageTaskRead)
def approve(task_id:int,data:ImageTransitionRequest,db:Session=Depends(get_db),user:User=Depends(require_roles("admin"))):
    try:return image_service.transition_task(db,user,_task(db,task_id),"approve",data.reason)
    except (ValueError,RuntimeError) as exc:_error(exc)
@router.post("/tasks/{task_id}/reject", response_model=ImageTaskRead)
def reject(task_id:int,data:ImageTransitionRequest,db:Session=Depends(get_db),user:User=Depends(require_roles("admin"))):
    try:return image_service.transition_task(db,user,_task(db,task_id),"reject",data.reason)
    except (ValueError,RuntimeError) as exc:_error(exc)
@router.post("/tasks/{task_id}/export", response_model=ImageExportRead)
def export(task_id:int,db:Session=Depends(get_db),user:User=Depends(require_roles("admin"))):
    try:return image_service.export_task(db,user,_task(db,task_id))
    except (ValueError,RuntimeError) as exc:_error(exc)

# Legacy aliases retain old service tests but still enforce M2 authorization.
@router.post("/upload", response_model=AssetRead, status_code=201)
def upload(product_id:int=Form(...),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(require_roles("admin","operator_content"))): return reference(product_id,file,db,user)
@router.get("/assets/{product_id}", response_model=AssetListResponse)
def assets(product_id:int, db:Session=Depends(get_db),_:User=Depends(require_roles("admin","operator_content"))):
    items=image_service.get_product_assets(db,product_id); return {"items":items,"total":len(items)}
