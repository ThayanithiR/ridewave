import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import assistant, auth, drivers, rides, websockets
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.services.location_cache import redis_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Isolated test/prototyping utility: In production, versioned Alembic migrations manage schema.
    if settings.AUTO_CREATE_TABLES and settings.APP_ENV != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="RideWave: High-concurrency, spatial ride-hailing API",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    lifespan=lifespan,
)

# Structured Request ID and Timing Middleware
@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()
    response: Response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    return response


# Narrow CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(drivers.router, prefix=settings.API_V1_PREFIX)
app.include_router(rides.router, prefix=settings.API_V1_PREFIX)
app.include_router(assistant.router, prefix=settings.API_V1_PREFIX)
app.include_router(websockets.router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "docs_url": f"{settings.API_V1_PREFIX}/docs",
        "api_v1": settings.API_V1_PREFIX,
    }


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health/ready", tags=["Health"])
async def readiness_check(response: Response):
    """Deep readiness check validating database and cache availability."""
    db_ok = False
    redis_ok = False

    # 1. Probe database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    # 2. Probe redis
    try:
        client = await redis_store.get_client()
        pong = await client.ping()
        redis_ok = bool(pong)
    except Exception:
        redis_ok = False

    is_ready = db_ok  # Database is hard dependency; Redis degrades gracefully
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "unhealthy",
        "database": "connected" if db_ok else "unreachable",
        "cache": "connected" if redis_ok else "degraded",
    }
