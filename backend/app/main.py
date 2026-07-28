"""EcomAgent Backend — FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.content import router as content_router, router_audit
from .api.images import router as image_router
from .api.products import router as product_router
from .api.auth import router as auth_router
from .api.costs import router as cost_router
from .api.customer_service import customer_router, service_router
from .core.config import settings
from .core.database import engine
from .core.schema_contract import assert_schema_current

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
app.include_router(content_router)
app.include_router(router_audit)
app.include_router(image_router)
app.include_router(auth_router)
app.include_router(cost_router)
app.include_router(customer_router)
app.include_router(service_router)

@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request, exc):
    fields = []
    for error in exc.errors():
        safe_error = {key: value for key, value in error.items() if key != "ctx"}
        if error.get("ctx"):
            safe_error["ctx"] = {
                key: str(value) for key, value in error["ctx"].items()
            }
        fields.append(safe_error)
    return JSONResponse(status_code=422, content={"detail":{"code":"validation_error", "message":"Request validation failed", "fields":fields}})

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
