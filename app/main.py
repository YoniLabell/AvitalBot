"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import admin, webhook
from app.storage import json_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    json_store.init_storage()
    yield


app = FastAPI(title="WhatsApp Flow Bot", version="0.1.0", lifespan=lifespan)

app.include_router(webhook.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Render's health check. Must stay cheap and must not call GREEN-API."""
    return {"status": "ok"}
