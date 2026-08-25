"""GREEN-API webhook endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.services import bot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook/green-api")
async def green_api_webhook(request: Request) -> dict[str, str]:
    """Always answer 200 so GREEN-API does not retry a notification forever."""
    try:
        payload: Any = await request.json()
    except ValueError:
        logger.warning("Webhook body was not valid JSON - ignoring")
        return {"status": "ignored"}

    if not isinstance(payload, dict):
        logger.warning("Webhook body was not a JSON object - ignoring")
        return {"status": "ignored"}

    try:
        await bot.handle_webhook(payload)
    except Exception:
        logger.exception("Failed to handle webhook %s", payload.get("typeWebhook"))
        return {"status": "error"}

    return {"status": "ok"}
