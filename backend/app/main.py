"""EcomAgent Backend — FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.content import router as content_router, router_audit
from .api.images import router as image_router
from .api.products import router as product_router
from .api.product_categories import router as product_category_router
from .api.auth import router as auth_router
from .api.costs import router as cost_router
from .api.customer_service import customer_router, service_router
from .core.config import settings
from .core.database import engine
from .core.schema_contract import assert_schema_current
from .services.image_service import UPLOAD_DIR

# Import all models so the read-only runtime schema contract sees every table.
import app.models.product  # noqa: F401
import app.models.content  # noqa: F401
import app.models.order    # noqa: F401
import app.models.asset    # noqa: F401
import app.models.user     # noqa: F401
import app.models.cost     # noqa: F401

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter — 100 requests per minute per IP."""

    RATE_LIMIT = 100
    WINDOW_SECONDS = 60

    def __init__(self, app):
        super().__init__(app)
        self._clients: dict[str, list[float]] = {}

    @staticmethod
    def _add_security_headers(response: JSONResponse) -> JSONResponse:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._clients.setdefault(client_ip, [])
        # Prune old entries
        self._clients[client_ip] = [
            t for t in self._clients[client_ip] if now - t < self.WINDOW_SECONDS
        ]
        if len(self._clients[client_ip]) >= self.RATE_LIMIT:
            return self._add_security_headers(
                JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                )
            )
        self._clients[client_ip].append(now)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-related HTTP response headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Normal runtime validates, but never mutates, the database schema."""
    assert_schema_current(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# CORS — allow frontend dev server (must be outermost for preflight handling)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Security headers (innermost — adds to all non-429 responses; 429 handled inline)
app.add_middleware(SecurityHeadersMiddleware)

# Register routers
app.include_router(product_router)
app.include_router(product_category_router)
app.include_router(content_router)
app.include_router(router_audit)
app.include_router(image_router)
app.include_router(auth_router)
app.include_router(cost_router)
app.include_router(customer_router)
app.include_router(service_router)


_VALIDATION_FIELD_LABELS = {
    "brand": "品牌",
    "category": "商品类目",
    "content": "消息内容",
    "content_type": "内容类型",
    "description": "商品描述",
    "detail": "商品详情",
    "faq": "FAQ",
    "inventory": "库存信息",
    "locked_quantity": "锁定库存数量",
    "marketing_allocation": "推广分摊",
    "after_sales_loss": "售后损失",
    "packaging_cost": "包装成本",
    "parameters": "参数说明",
    "parameters_json": "商品参数",
    "password": "密码",
    "platform": "平台",
    "platform_fee": "平台扣点",
    "product_id": "商品",
    "promo_material": "图文推广素材",
    "purchase_cost": "采购成本",
    "reference_asset_id": "参考图",
    "reason": "原因",
    "safety_stock": "安全库存数量",
    "sales_script": "售前话术",
    "selling_points": "卖点",
    "shipping_rule_text": "发货规则",
    "shipping_subsidy": "运费补贴",
    "sku_name": "SKU名称",
    "skus": "SKU列表",
    "spec": "SKU规格",
    "status": "状态",
    "stock_quantity": "库存数量",
    "style": "图片场景",
    "title": "标题",
    "username": "用户名",
}
_SUPPORTED_VALIDATION_TYPES = {
    "missing",
    "string_too_short",
    "string_too_long",
    "greater_than_equal",
    "finite_number",
    "float_parsing",
    "int_parsing",
    "list_type",
    "dict_type",
    "enum",
    "literal_error",
}
_SAFE_VALIDATION_FALLBACK = {
    "field": "请求参数",
    "message": "输入内容不符合要求",
}


def _validation_field_name(request: Request, location: object) -> str | None:
    if not isinstance(location, (list, tuple)):
        return None
    parts = [part for part in location if part not in {"body", "query", "path"}]
    if not parts:
        return None

    path = getattr(getattr(request, "url", None), "path", "")
    last = parts[-1]
    if last == "name":
        return "类目名称" if path.startswith("/api/product-categories") else "商品名称"
    if last == "price":
        base_name = "SKU零售价"
    elif isinstance(last, str):
        base_name = _VALIDATION_FIELD_LABELS.get(last)
    else:
        base_name = None
    if base_name is None:
        return None

    try:
        sku_position = parts.index("skus")
    except ValueError:
        return base_name
    if sku_position + 1 >= len(parts):
        return base_name
    sku_index = parts[sku_position + 1]
    if isinstance(sku_index, str) and sku_index.isdigit():
        sku_index = int(sku_index)
    if not isinstance(sku_index, int) or sku_index < 0:
        return base_name
    return f"第{sku_index + 1}个SKU{base_name.removeprefix('SKU')}"


def _safe_validation_field(request: Request, error: object) -> dict[str, str]:
    if not isinstance(error, dict):
        return dict(_SAFE_VALIDATION_FALLBACK)
    error_type = error.get("type")
    field = _validation_field_name(request, error.get("loc"))
    if error_type not in _SUPPORTED_VALIDATION_TYPES or field is None:
        return dict(_SAFE_VALIDATION_FALLBACK)

    if error_type == "missing":
        message = (
            "请选择有效的商品类目"
            if field == "商品类目"
            else f"请填写{field}"
        )
    elif error_type == "string_too_short":
        message = (
            "请选择有效的商品类目"
            if field == "商品类目"
            else f"{field}不能为空"
        )
    elif error_type == "string_too_long":
        message = f"{field}长度超出限制"
    elif error_type == "greater_than_equal":
        message = (
            f"{field}不能小于0"
            if any(label in field for label in ("零售价", "成本", "库存"))
            else f"{field}低于允许范围"
        )
    elif error_type == "finite_number":
        message = f"{field}必须是有限数字"
    elif error_type == "float_parsing":
        message = f"{field}必须是有效数字"
    elif error_type == "int_parsing":
        message = f"{field}必须是整数"
    elif error_type == "list_type":
        message = f"{field}必须是列表"
    elif error_type == "dict_type":
        message = f"{field}格式不正确"
    else:
        message = f"{field}的取值不符合要求"
    return {"field": field, "message": message}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    try:
        fields = [_safe_validation_field(request, error) for error in exc.errors()]
    except Exception:
        fields = []
    if not fields:
        fields = [dict(_SAFE_VALIDATION_FALLBACK)]
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "validation_error",
                "message": "请求参数校验失败",
                "fields": fields,
            }
        },
    )

@app.exception_handler(HTTPException)
async def http_error_handler(_request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code":"not_found" if exc.status_code == 404 else "request_error", "message":str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"detail":detail})

@app.exception_handler(StarletteHTTPException)
async def starlette_error_handler(_request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code":"not_found" if exc.status_code == 404 else "request_error", "message":str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"detail":detail})


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}
