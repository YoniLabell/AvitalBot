"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routers import admin, webhook
from app.services import bot
from app.storage import json_store

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)


def log_configuration() -> None:
    """Report the configuration at startup. Never logs a secret's value."""
    logger.info("WhatsApp flow bot starting")
    logger.info("  GREEN_API_API_URL     = %s", settings.green_api_api_url)
    logger.info("  GREEN_API_INSTANCE_ID = %s", settings.green_api_instance_id or "(not set)")
    logger.info("  GREEN_API_TOKEN       = %s", "set" if settings.green_api_token else "(not set)")
    logger.info("  ADMIN_API_KEY         = %s", "set" if settings.admin_api_key else "(not set)")
    logger.info("  GREEN_API_MEDIA_URL   = %s", settings.green_api_media_url)
    logger.info("  DATA_FILE_PATH        = %s", settings.data_file_path)
    logger.info("  ASSETS_DIR            = %s", settings.assets_dir)
    logger.info("  LOG_LEVEL             = %s", settings.log_level)

    for problem in settings.configuration_problems():
        logger.error("CONFIG PROBLEM: %s", problem)
    for missing in bot.missing_answer_images():
        logger.error("CONFIG PROBLEM: image file not found for %s", missing)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_configuration()
    json_store.init_storage()
    logger.info("Storage ready at %s", settings.data_file_path)
    yield


app = FastAPI(title="WhatsApp Flow Bot", version="0.1.0", lifespan=lifespan)

app.include_router(webhook.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Render's health check. Must stay cheap and must not call GREEN-API."""
    return {"status": "ok"}
