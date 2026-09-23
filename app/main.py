from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.database.connection import Base, engine
from app.api import routes_chat, routes_patients, routes_vapi


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": "An unexpected error occurred."},
    )
