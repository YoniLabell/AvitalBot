"""GREEN-API webhook endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.services import bot, green_api

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


async def _ignore_reason(payload: dict[str, Any]) -> str | None:
    """Allow only incoming messages from numbers not saved in the phone book.

    senderContactName is the *saved phone-book name*, not the WhatsApp profile
    name. Cross-check unknown/unsaved senders with GetContactInfo so a missing
    webhook field cannot accidentally cause a reply to a saved contact.
    If verification fails, fail closed: never risk messaging an existing client.
    """
    if payload.get("typeWebhook") != bot.INCOMING_MESSAGE:
        return None

    sender = payload.get("senderData") or {}
    chat_id = sender.get("chatId")
    if not isinstance(chat_id, str) or not chat_id.endswith(("@c.us", "@lid")):
        return "not a one-to-one WhatsApp chat"

    saved_name = sender.get("senderContactName")
    if isinstance(saved_name, str) and saved_name.strip():
        return "sender is saved in phone contacts (webhook)"

    try:
        info = await green_api.get_contact_info(chat_id)
    except green_api.GreenAPIError as exc:
        logger.warning("Cannot check whether %s is saved; ignoring to avoid messaging contacts: %s", chat_id, exc)
        return "unable to verify contact is unsaved"

    # GREEN-API GetContactInfo: contactName = phone book entry, while name
    # is only the user's WhatsApp profile name (and must NOT be used here).
    contact_name = info.get("contactName")
    if not isinstance(contact_name, str):
        logger.warning("GetContactInfo for %s did not include contactName; ignoring", chat_id)
        return "contact book status unknown"
    if contact_name.strip():
        return "sender is saved in phone contacts (GetContactInfo)"

    return None

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

    ignore_reason = await _ignore_reason(payload)
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
