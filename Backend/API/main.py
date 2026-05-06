"""
Is It In? — FastAPI entry point.

Run from the project root:
    uvicorn Backend.API.main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from Backend.API.config import CORS_ORIGINS
from Backend.API.routes import river_requests, rivers
from Backend.API.services.predictions import warmup
from ML.rivers import RIVERS

PWA_DIST = Path(__file__).resolve().parents[2] / "Frontend" / "dist"
PWA_MOUNT = "/is-it-in"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run warmup in a background thread so the port binds immediately.
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=1), warmup
    )
    yield


app = FastAPI(title="Is It In?", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rivers.router)
app.include_router(river_requests.router)


@app.get("/")
def root():
    return {"message": "Is It In? API", "docs": "/docs", "rivers": list(RIVERS.keys())}


# PWA bundle served at /is-it-in. html=True makes "/is-it-in/" return index.html.
# Mounted last so it can't shadow API routes at the root.
if PWA_DIST.is_dir():
    app.mount(PWA_MOUNT, StaticFiles(directory=PWA_DIST, html=True), name="pwa")
