from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assistant, auth, drivers, rides, websockets
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="RideWave: High-concurrency, spatial ride-hailing API",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
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


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    return {"status": "ready"}
