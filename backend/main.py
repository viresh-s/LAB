# backend/main.py
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.graph.builder import create_voice_graph
from app.graph.state import PatientData
from app.api.webhooks import router as webhook_router
from app.api.stream import router as stream_router
from app.api.lab_api import router as lab_router
from app.api.admin_api import router as admin_router

import logging
import time
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Security Headers Middleware
# ─────────────────────────────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # XSS Protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy — don't leak full URLs
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions policy — disable unused browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # HSTS (Strict-Transport-Security)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Content-Security-Policy
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        # Prevent caching of authenticated responses
        if request.headers.get("Authorization"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Request Size Limiting Middleware
# ─────────────────────────────────────────────────────────────────────────────
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limits the maximum size of incoming requests (e.g. 20MB max to allow PDFs but block abuse)."""
    def __init__(self, app, max_bytes: int = 20 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        if request.headers.get('content-length'):
            try:
                content_length = int(request.headers['content-length'])
                if content_length > self.max_bytes:
                    return Response(
                        content='{"detail": "Request body too large"}',
                        status_code=413,
                        media_type="application/json"
                    )
            except ValueError:
                pass
        return await call_next(request)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiting Middleware (simple in-memory, per-IP)
# ─────────────────────────────────────────────────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP rate limiter: max requests per window."""
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ("/", "/health"):
            return await call_next(request)
        
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Clean old entries
        if client_ip in self._requests:
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] 
                if now - t < self.window_seconds
            ]
        else:
            self._requests[client_ip] = []
        
        if len(self._requests[client_ip]) >= self.max_requests:
            log.warning("[rate_limit] IP %s exceeded %d requests in %ds", 
                       client_ip, self.max_requests, self.window_seconds)
            return Response(
                content='{"detail": "Too many requests. Please try again later."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(self.window_seconds)}
            )
        
        self._requests[client_ip].append(now)
        
        # Periodically clean up old IPs (every 1000 requests)
        if sum(len(v) for v in self._requests.values()) > 10000:
            cutoff = now - self.window_seconds
            self._requests = {
                ip: [t for t in times if t > cutoff]
                for ip, times in self._requests.items()
                if any(t > cutoff for t in times)
            }
        
        return await call_next(request)


# ─────────────────────────────────────────────────────────────────────────────
# Request Logging Middleware
# ─────────────────────────────────────────────────────────────────────────────
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request method, path, response status, and duration."""
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        
        # Only log non-health endpoints or slow requests
        if request.url.path not in ("/", "/health") or duration > 1.0:
            log.info(
                "[request] %s %s → %d (%.2fs) client=%s",
                request.method, request.url.path, response.status_code,
                duration, request.client.host if request.client else "?"
            )
        return response


# ─────────────────────────────────────────────────────────────────────────────
# App Initialization
# ─────────────────────────────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

from contextlib import asynccontextmanager
import asyncio
from cron_cleanup import run_cleanup
from datetime import datetime

async def cleanup_loop():
    while True:
        now = datetime.now()
        # Run cleanup around 11 PM daily
        if now.hour == 23:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, run_cleanup)
            except Exception as e:
                log.error("Background cleanup task failed: %s", e)
        # Sleep for 1 hour
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()

app = FastAPI(
    title="Lab Booking SaaS Backend",
    docs_url=None if ENVIRONMENT == "production" else "/docs",
    redoc_url=None if ENVIRONMENT == "production" else "/redoc",
    lifespan=lifespan
)

# Middleware order matters — outermost first
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=20 * 1024 * 1024)  # 20MB limit
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# Allow cross-origin requests
allowed_origins = [FRONTEND_URL] if ENVIRONMENT == "production" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "lab-password"],
    expose_headers=["X-Request-ID"],
    max_age=3600,
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(webhook_router, prefix="/webhooks")
app.include_router(stream_router, prefix="/webhooks")
app.include_router(lab_router)
app.include_router(admin_router)

@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Lab Booking SaaS API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
