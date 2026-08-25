"""Predefined WhatsApp conversation flows.

This is not an AI chatbot: every reply is chosen by the rules below. All
customer-facing wording lives in app/messages/, and all state lives behind
app/storage/json_store.py.
"""

from __future__ import annotations

import logging
from typing import Any

from app.messages import catalogue
from app.services import green_api
from app.storage import json_store

logger = logging.getLogger(__name__)

# Onboarding stages stored as user["step"].
STEP_NEW = 0
STEP_AWAITING_LANGUAGE = 1
STEP_AWAITING_INTEREST = 2
STEP_DONE = 3

LANGUAGE_CHOICES = {
    "1": "he",
    "2": "en",
    "עברית": "he",
    "hebrew": "he",
    "english": "en",
}

INTEREST_CHOICES = {
    "1": "pilates",
    "2": "barre",
    "3": "instructor_course",
    "4": "other",
}

# Webhook types we act on (green-api.com/en/docs/api/receiving/notifications-format/type-webhook/).
INCOMING_MESSAGE = "incomingMessageReceived"
OUTGOING_MANUAL_MESSAGE = "outgoingMessageReceived"
OUTGOING_API_MESSAGE = "outgoingAPIMessageReceived"


def handover_to_human(chat_id: str) -> None:
    """Stop automatic replies for this customer - a human is handling the chat."""
    json_store.update_user(chat_id, {"flow": "human", "bot_enabled": False})
    logger.info("Handed chat %s over to a human", chat_id)


def extract_text(message_data: dict[str, Any]) -> str | None:
    """Pull the text out of a GREEN-API messageData block, if it holds any."""
    if not isinstance(message_data, dict):
        return None

    type_message = message_data.get("typeMessage")
    if type_message == "textMessage":
        block = message_data.get("textMessageData") or {}
        text = block.get("textMessage")
    elif type_message in ("extendedTextMessage", "quotedMessage"):
        block = message_data.get("extendedTextMessageData") or {}
        text = block.get("text")
    else:
        return None

    return text if isinstance(text, str) else None


def _normalize(text: str) -> str:
    """Reduce a reply to something we can match a menu option against."""
    return text.strip().lower().rstrip(".)")


async def _send_all(chat_id: str, messages: list[str]) -> None:
    for message in messages:
        await green_api.send_text(chat_id, message)


async def _start_onboarding(chat_id: str) -> None:
    messages = catalogue(None)
    json_store.update_user(
        chat_id,
        {"language": None, "flow": None, "step": STEP_AWAITING_LANGUAGE},
    )
    await green_api.send_text(chat_id, messages.LANGUAGE_MENU)


async def _handle_language_choice(chat_id: str, text: str) -> None:
    language = LANGUAGE_CHOICES.get(_normalize(text))
    if language is None:
        messages = catalogue(None)
        await green_api.send_text(chat_id, messages.INVALID_LANGUAGE_CHOICE)
        await green_api.send_text(chat_id, messages.LANGUAGE_MENU)
        return

    json_store.update_user(chat_id, {"language": language, "step": STEP_AWAITING_INTEREST})
    await green_api.send_text(chat_id, catalogue(language).INTEREST_MENU)


async def _handle_interest_choice(chat_id: str, language: str | None, text: str) -> None:
    messages = catalogue(language)
    flow = INTEREST_CHOICES.get(_normalize(text))
    if flow is None:
        await green_api.send_text(chat_id, messages.INVALID_INTEREST_CHOICE)
        await green_api.send_text(chat_id, messages.INTEREST_MENU)
        return

    json_store.update_user(chat_id, {"flow": flow, "step": STEP_DONE})
    await _send_all(chat_id, messages.FLOW_MESSAGES[flow])


async def handle_incoming_message(chat_id: str, message_id: str, text: str) -> None:
    """Advance the flow for one incoming customer text message."""
    user = json_store.get_user(chat_id)

    if user is None:
        # A chatId we have never seen is a new inquiry.
        json_store.create_user(chat_id)
        json_store.mark_message_processed(chat_id, message_id)
        await _start_onboarding(chat_id)
        return

    json_store.mark_message_processed(chat_id, message_id)

    if not user.get("bot_enabled", True):
        logger.info("Bot disabled for %s - ignoring incoming message", chat_id)
        return

    step = user.get("step", STEP_NEW)
    if step in (STEP_NEW, STEP_AWAITING_LANGUAGE):
        if step == STEP_NEW:
            await _start_onboarding(chat_id)
        else:
            await _handle_language_choice(chat_id, text)
    elif step == STEP_AWAITING_INTEREST:
        await _handle_interest_choice(chat_id, user.get("language"), text)
    else:
        # Onboarding is finished. Never restart it automatically - from here on
        # the business owner answers, and their first manual reply arrives as
        # outgoingMessageReceived and disables the bot for good.
        logger.info("Onboarding complete for %s - no automatic reply", chat_id)


async def handle_webhook(payload: dict[str, Any]) -> None:
    """Route one GREEN-API notification. Unknown types are ignored on purpose."""
    type_webhook = payload.get("typeWebhook")
    chat_id = (payload.get("senderData") or {}).get("chatId")

    if type_webhook == OUTGOING_MANUAL_MESSAGE:
        # Sent by the owner from WhatsApp / Web / Desktop - a human took over.
        if chat_id:
            handover_to_human(chat_id)
        return

    if type_webhook == OUTGOING_API_MESSAGE:
        # Our own message, sent through GREEN-API. Never a human takeover.
        logger.debug("Ignoring our own outgoing API message to %s", chat_id)
        return

    if type_webhook != INCOMING_MESSAGE:
        logger.debug("Ignoring webhook type %s", type_webhook)
        return

    message_id = payload.get("idMessage")
    if not chat_id or not message_id:
        logger.warning("Incoming webhook without chatId or idMessage - ignoring")
        return

    text = extract_text(payload.get("messageData") or {})
    if text is None:
        logger.info("Non-text message from %s - ignoring", chat_id)
        return

    if json_store.has_processed_message(chat_id, message_id):
        logger.info("Duplicate notification %s for %s - ignoring", message_id, chat_id)
        return

    await handle_incoming_message(chat_id, message_id, text)
