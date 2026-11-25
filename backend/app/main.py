from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import error_envelope, register_exception_handlers
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.base import Base
from app.db.session import engine

settings = get_settings()
setup_logging()
logger = get_logger(__name__)
rate_limiter = SlidingWindowRateLimiter(max_requests=settings.RATE_LIMIT_PER_MINUTE, window_seconds=60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("VisionGuard Tutor API started")
    yield
    logger.info("VisionGuard Tutor API shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_observability_middleware(request: Request, call_next) -> Response:
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_ctx.set(req_id)
    try:
        client_ip = request.client.host if request.client else "unknown"
        if not request.url.path.endswith("/healthz"):
            allowed, retry_after = rate_limiter.allow(client_ip)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "X-Request-ID": req_id},
                    content=error_envelope(
                        "RATE_LIMIT_EXCEEDED",
                        "Too many requests. Please slow down and try again.",
                        {"retry_after_seconds": retry_after},
                    ),
                )

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
    finally:
        request_id_ctx.reset(token)


register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")
