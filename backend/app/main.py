from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assistant, auth, drivers, rides, websockets
from app.core.config import settings
from app.core.database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create tables on startup if they don't exist
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
async def readiness_check():
    return {"status": "ready"}
