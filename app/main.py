from contextlib import asynccontextmanager
import asyncio
import httpx
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.database.connection import Base, engine
from app.api import routes_chat, routes_patients, routes_vapi

logger = logging.getLogger(__name__)
RAILWAY_URL = "https://web-production-82a93.up.railway.app"


async def _keep_warm():
    """Ping self every 4 minutes to prevent Railway cold starts."""
    await asyncio.sleep(30)  # wait for app to fully start
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(f"{RAILWAY_URL}/health", timeout=10)
            except Exception:
                pass
            await asyncio.sleep(240)  # 4 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    asyncio.create_task(_keep_warm())
    yield


app = FastAPI(
    title="Patient Registration AI Agent",
    description="Conversational AI agent for patient registration",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(routes_chat.router)
app.include_router(routes_patients.router)
app.include_router(routes_vapi.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": "An unexpected error occurred."},
    )
