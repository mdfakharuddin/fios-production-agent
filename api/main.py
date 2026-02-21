import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes.chat import router as chat_router
from api.routes.job import router as job_router
from core.scheduler import global_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    global_scheduler.start()
    yield

app = FastAPI(
    title="FIOS Intelligence API",
    version="1.0.0",
    lifespan=lifespan
)

# Allow Chrome extension & web UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routes
app.include_router(
    chat_router,
    prefix="/fios/api"
)

app.include_router(
    job_router,
    prefix="/fios/api/job"
)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "FIOS Intelligence API"
    }
