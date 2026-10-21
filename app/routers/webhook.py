"""GREEN-API webhook endpoint."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Request, Response

from app.services import bot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

# TEMPORARY QUEUE DRAIN MODE: acknowledge every webhook with an empty HTTP 200
# without running the bot or sending any WhatsApp message. Enabled by default
# for the current backlog. Set DRAIN_QUEUE_MODE=false in Render to resume.
DRAIN_QUEUE_MODE = os.getenv("DRAIN_QUEUE_MODE", "true").strip().lower() in {
    "1", "true", "yes", "on"
}


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


def _ignore_reason(payload: dict[str, Any]) -> str | None:
    """Return why an incoming chat should not reach the bot, if any.

    AvitalBot is meant only for new leads. GREEN-API exposes
    senderContactName from the current WhatsApp account's contacts, so
    existing saved contacts are left to the studio owner. Group chats are
    ignored as well.
    """
    if payload.get("typeWebhook") != bot.INCOMING_MESSAGE:
        return None

    sender = payload.get("senderData") or {}
    chat_id = sender.get("chatId")

    if isinstance(chat_id, str) and chat_id.endswith("@g.us"):
        return "WhatsApp group"

    sender_contact_name = sender.get("senderContactName")
    if isinstance(sender_contact_name, str) and sender_contact_name.strip():
        return "sender is saved in contacts"

    return None


@router.post("/webhook/green-api")
async def green_api_webhook(request: Request) -> dict[str, str] | Response:
    """Always answer 200 so GREEN-API does not retry a notification forever."""
    if DRAIN_QUEUE_MODE:
        # GREEN-API removes acknowledged notifications from its incoming queue.
        # No body, no bot processing, and no outgoing WhatsApp messages.
        return Response(status_code=200)
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

    ignore_reason = _ignore_reason(payload)
    if ignore_reason is not None:
        logger.info("Webhook ignored: %s (%s)", _summary(payload), ignore_reason)
        return {"status": "ignored", "reason": ignore_reason}

    try:
        await bot.handle_webhook(payload)
    except Exception as exc:
        # Still a 200: retrying will not fix a bug, and GREEN-API would keep
        # redelivering forever. The log line below is the thing to read.
        logger.exception("Failed to handle webhook (%s)", _summary(payload))
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}

    return {"status": "ok"}
