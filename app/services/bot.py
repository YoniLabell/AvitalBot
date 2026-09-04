"""Predefined WhatsApp conversation flows.

This is not an AI chatbot: every reply is chosen by the rules below. All
customer-facing wording lives in app/messages/, and all state lives behind
app/storage/json_store.py.

Menus are sent as GREEN-API interactive buttons. That method is beta, so every
menu falls back to the same wording as a numbered text message, and a customer
who types "1" instead of tapping is always understood.
"""

from __future__ import annotations

import logging
from typing import Any

from app.messages import catalogue, menu_as_text
from app.services import green_api
from app.storage import json_store

logger = logging.getLogger(__name__)

# Onboarding stages stored as user["step"].
STEP_NEW = 0
STEP_AWAITING_LANGUAGE = 1
STEP_AWAITING_INTEREST = 2
STEP_DONE = 3

# buttonId -> stored value. The ids match the button order in app/messages/.
LANGUAGE_BY_BUTTON_ID = {"1": "he", "2": "en"}
FLOW_BY_BUTTON_ID = {"1": "pilates", "2": "barre", "3": "instructor_course"}

# Extra text a customer might type instead of tapping a language button.
LANGUAGE_ALIASES = {"עברית": "he", "hebrew": "he", "english": "en", "אנגלית": "en"}

# Webhook types we act on (green-api.com/en/docs/api/receiving/notifications-format/type-webhook/).
INCOMING_MESSAGE = "incomingMessageReceived"
OUTGOING_MANUAL_MESSAGE = "outgoingMessageReceived"
OUTGOING_API_MESSAGE = "outgoingAPIMessageReceived"


def handover_to_human(chat_id: str) -> None:
    """Stop automatic replies for this customer - a human is handling the chat."""
    json_store.update_user(chat_id, {"flow": "human", "bot_enabled": False})
    logger.info("Handed chat %s over to a human", chat_id)


def extract_reply(message_data: dict[str, Any]) -> str | None:
    """Pull the customer's answer out of a GREEN-API messageData block.

    Returns the typed text, or - when the customer tapped a button - the id or
    label of that button. Both are matched against the menu by _match_choice.
    """
    if not isinstance(message_data, dict):
        return None

    type_message = message_data.get("typeMessage")

    if type_message == "textMessage":
        block = message_data.get("textMessageData") or {}
        return _as_text(block.get("textMessage"))

    if type_message in ("extendedTextMessage", "quotedMessage"):
        block = message_data.get("extendedTextMessageData") or {}
        return _as_text(block.get("text"))

    # A tapped button. GREEN-API reports these under a few different names
    # depending on how the menu was sent, so check the known shapes.
    for key in ("interactiveButtonsReply", "buttonsResponseMessage", "templateButtonReplyMessage"):
        block = message_data.get(key)
        if not isinstance(block, dict):
            continue
        for field in ("selectedButtonId", "selectedId", "selectedButtonText", "selectedDisplayText"):
            value = _as_text(block.get(field))
            if value:
                return value
        # Some notifications carry the tapped button as a single-entry list.
        buttons = block.get("buttons")
        if isinstance(buttons, list) and len(buttons) == 1 and isinstance(buttons[0], dict):
            return _as_text(buttons[0].get("buttonId")) or _as_text(buttons[0].get("buttonText"))

    return None


def _as_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _normalize(text: str) -> str:
    """Reduce a reply to something we can match a menu option against."""
    return text.strip().lower().rstrip(".)")


def _match_choice(
    reply: str,
    buttons: list[dict[str, Any]],
    by_button_id: dict[str, str],
    aliases: dict[str, str] | None = None,
) -> str | None:
    """Resolve a reply to a menu value, whether it was tapped or typed."""
    token = _normalize(reply)

    if token in by_button_id:
        return by_button_id[token]

    for button in buttons:
        if token == _normalize(button["buttonText"]):
            return by_button_id.get(button["buttonId"])

    return (aliases or {}).get(token)


async def _send_menu(chat_id: str, body: str, buttons: list[dict[str, Any]]) -> None:
    """Send a menu as interactive buttons, falling back to numbered text."""
    try:
        await green_api.send_buttons(chat_id, body, buttons)
    except green_api.GreenAPIError:
        logger.warning("Button menu failed for %s - sending the text menu instead", chat_id)
        await green_api.send_text(chat_id, menu_as_text(body, buttons))


async def _send_all(chat_id: str, messages: list[str]) -> None:
    for message in messages:
        await green_api.send_text(chat_id, message)


async def _start_onboarding(chat_id: str) -> None:
    messages = catalogue(None)
    json_store.update_user(
        chat_id,
        {"language": None, "flow": None, "step": STEP_AWAITING_LANGUAGE},
    )
    await _send_menu(chat_id, messages.LANGUAGE_BODY, messages.LANGUAGE_BUTTONS)


async def _handle_language_choice(chat_id: str, reply: str) -> None:
    messages = catalogue(None)
    language = _match_choice(
        reply, messages.LANGUAGE_BUTTONS, LANGUAGE_BY_BUTTON_ID, LANGUAGE_ALIASES
    )
    if language is None:
        await green_api.send_text(chat_id, messages.INVALID_LANGUAGE_CHOICE)
        await _send_menu(chat_id, messages.LANGUAGE_BODY, messages.LANGUAGE_BUTTONS)
        return

    json_store.update_user(chat_id, {"language": language, "step": STEP_AWAITING_INTEREST})
    chosen = catalogue(language)
    await _send_menu(chat_id, chosen.INTEREST_BODY, chosen.INTEREST_BUTTONS)


async def _handle_interest_choice(chat_id: str, language: str | None, reply: str) -> None:
    messages = catalogue(language)
    flow = _match_choice(reply, messages.INTEREST_BUTTONS, FLOW_BY_BUTTON_ID)
    if flow is None:
        await green_api.send_text(chat_id, messages.INVALID_INTEREST_CHOICE)
        await _send_menu(chat_id, messages.INTEREST_BODY, messages.INTEREST_BUTTONS)
        return

    json_store.update_user(chat_id, {"flow": flow, "step": STEP_DONE})
    await _send_all(chat_id, messages.FLOW_MESSAGES[flow])


async def handle_incoming_message(chat_id: str, message_id: str, reply: str) -> None:
    """Advance the flow for one incoming customer message."""
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
    if step == STEP_NEW:
        await _start_onboarding(chat_id)
    elif step == STEP_AWAITING_LANGUAGE:
        await _handle_language_choice(chat_id, reply)
    elif step == STEP_AWAITING_INTEREST:
        await _handle_interest_choice(chat_id, user.get("language"), reply)
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

    reply = extract_reply(payload.get("messageData") or {})
    if reply is None:
        logger.info("Unsupported message type from %s - ignoring", chat_id)
        return

    if json_store.has_processed_message(chat_id, message_id):
        logger.info("Duplicate notification %s for %s - ignoring", message_id, chat_id)
        return

    await handle_incoming_message(chat_id, message_id, reply)
