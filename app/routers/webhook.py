"""GREEN-API webhook endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.services import bot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


def _summary(payload: dict[str, Any]) -> str:
    """One-line description of a notification, for the log."""
    sender = payload.get("senderData") or {}
    message_data = payload.get("messageData") or {}
    return (
        f"type={payload.get('typeWebhook')!r} "
        f"chatId={sender.get('chatId')!r} "
        f"idMessage={payload.get('idMessage')!r} "
        f"typeMessage={message_data.get('typeMessage')!r}"
    )


@router.post("/webhook/green-api")
async def green_api_webhook(request: Request) -> dict[str, str]:
    """Always answer 200 so GREEN-API does not retry a notification forever."""
    try:
        payload: Any = await request.json()
    except ValueError:
        raw = (await request.body())[:500]
        logger.warning("Webhook body was not valid JSON - ignoring. Body: %r", raw)
        return {"status": "ignored", "reason": "body is not valid JSON"}

    if not isinstance(payload, dict):
        logger.warning("Webhook body was %s, expected an object - ignoring", type(payload).__name__)
        return {"status": "ignored", "reason": "body is not a JSON object"}

    logger.info("Webhook received: %s", _summary(payload))
    logger.debug("Webhook full body: %s", payload)

    try:
        await bot.handle_webhook(payload)
    except Exception as exc:
        # Still a 200: retrying will not fix a bug, and GREEN-API would keep
        # redelivering forever. The log line below is the thing to read.
        logger.exception("Failed to handle webhook (%s)", _summary(payload))
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}

    return {"status": "ok"}
