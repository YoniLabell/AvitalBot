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
STEP_AWAITING_DETAIL = 3
STEP_FINISHED = 4

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


# Sub-objects of messageData that can carry a tapped button, and the keys
# inside them that hold the customer's choice. Confirmed against
# green-api.com/en/docs/api/receiving/notifications-format/selected-buttons/:
#   buttonsResponseMessage      {stanzaId, selectedButtonId, selectedButtonText}
#   templateButtonsReplyMessage {stanzaId, selectedIndex, selectedId, selectedDisplayText}
#   listResponseMessage         the chosen row, under singleSelectReply
# interactiveButtonsReply is the *menu* arriving as a message, not a tap, so it
# normally carries no selection - it is scanned last, just in case.
BUTTON_REPLY_TYPES = (
    "buttonsResponseMessage",
    "templateButtonsReplyMessage",
    "listResponseMessage",
    "interactiveButtonsReply",
)

SELECTION_KEYS = (
    "selectedButtonId",
    "selectedId",
    "selectedRowId",
    "selectedButtonText",
    "selectedDisplayText",
)


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

    choice = _extract_button_choice(message_data)
    if choice is not None:
        return choice

    if type_message in BUTTON_REPLY_TYPES:
        # A button-shaped notification we could not read. Log the whole block:
        # this is the one thing needed to add support for its shape.
        logger.warning(
            "Could not tell which button was tapped in a %s. Full messageData: %s",
            type_message,
            message_data,
        )
    return None


def _extract_button_choice(message_data: dict[str, Any]) -> str | None:
    """Find the tapped button's id or label, whatever shape it arrived in."""
    for key in BUTTON_REPLY_TYPES:
        block = message_data.get(key)
        if not isinstance(block, dict):
            continue

        # listResponseMessage nests the chosen row one level down.
        for candidate in (block, block.get("singleSelectReply")):
            if not isinstance(candidate, dict):
                continue
            for field in SELECTION_KEYS:
                value = candidate.get(field)
                if value not in (None, ""):
                    return str(value).strip()

        # An unambiguous single-button payload: that button is the tapped one.
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


def _match_button_id(reply: str, buttons: list[dict[str, Any]]) -> str | None:
    """Which of these buttons the customer picked, by id or by label."""
    identity = {button["buttonId"]: button["buttonId"] for button in buttons}
    return _match_choice(reply, buttons, identity)


async def _send_menu(chat_id: str, body: str, buttons: list[dict[str, Any]]) -> None:
    """Send a menu as interactive buttons, falling back to numbered text."""
    try:
        await green_api.send_buttons(chat_id, body, buttons)
    except green_api.GreenAPIError as exc:
        logger.warning(
            "Button menu failed for %s (%s) - falling back to the numbered text menu",
            chat_id,
            exc,
        )
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
        logger.info("Unrecognised language choice from %s: %r - repeating menu", chat_id, reply)
        await green_api.send_text(chat_id, messages.INVALID_LANGUAGE_CHOICE)
        await _send_menu(chat_id, messages.LANGUAGE_BODY, messages.LANGUAGE_BUTTONS)
        return

    logger.info("%s chose language %s", chat_id, language)
    json_store.update_user(chat_id, {"language": language, "step": STEP_AWAITING_INTEREST})
    chosen = catalogue(language)
    await _send_menu(chat_id, chosen.INTEREST_BODY, chosen.INTEREST_BUTTONS)


async def _handle_interest_choice(chat_id: str, language: str | None, reply: str) -> None:
    messages = catalogue(language)
    flow = _match_choice(reply, messages.INTEREST_BUTTONS, FLOW_BY_BUTTON_ID)
    if flow is None:
        logger.info("Unrecognised interest choice from %s: %r - repeating menu", chat_id, reply)
        await green_api.send_text(chat_id, messages.INVALID_INTEREST_CHOICE)
        await _send_menu(chat_id, messages.INTEREST_BODY, messages.INTEREST_BUTTONS)
        return

    logger.info("%s chose flow %s", chat_id, flow)
    json_store.update_user(chat_id, {"flow": flow, "step": STEP_AWAITING_DETAIL})
    await _send_menu(chat_id, messages.FLOW_BODY[flow], messages.FLOW_BUTTONS[flow])


async def _handle_detail_choice(
    chat_id: str, language: str | None, flow: str | None, reply: str
) -> None:
    """Answer the follow-up question inside a flow, or fetch a human."""
    messages = catalogue(language)
    buttons = messages.FLOW_BUTTONS.get(flow or "")
    if not buttons:
        logger.error("No sub-menu defined for flow %r - nothing to answer", flow)
        return

    button_id = _match_button_id(reply, buttons)
    if button_id is None:
        logger.info("Unrecognised %s choice from %s: %r - repeating menu", flow, chat_id, reply)
        await green_api.send_text(chat_id, messages.INVALID_INTEREST_CHOICE)
        await _send_menu(chat_id, messages.FLOW_BODY[flow], buttons)
        return

    if button_id in messages.HANDOVER_BUTTONS.get(flow, set()):
        logger.info("%s asked to talk to a human (%s)", chat_id, flow)
        await green_api.send_text(chat_id, messages.HANDOVER_MESSAGE)
        handover_to_human(chat_id)
        return

    logger.info("%s chose %s option %s", chat_id, flow, button_id)
    json_store.update_user(chat_id, {"step": STEP_FINISHED})
    await _send_all(chat_id, messages.FLOW_ANSWERS[flow][button_id])


async def handle_incoming_message(chat_id: str, message_id: str, reply: str) -> None:
    """Advance the flow for one incoming customer message.

    The message is marked processed only after it has been handled without
    error, so that a send failure lets GREEN-API's retry reach the customer
    instead of being silently dropped as a duplicate.
    """
    user = json_store.get_user(chat_id)

    if user is None:
        # A chatId we have never seen is a new inquiry.
        logger.info("New customer %s - starting onboarding", chat_id)
        json_store.create_user(chat_id)
        try:
            await _start_onboarding(chat_id)
        except Exception:
            # Roll back so the retry is treated as a new inquiry again.
            logger.exception("Onboarding failed for %s - removing the new record", chat_id)
            json_store.reset_user(chat_id)
            raise
        json_store.mark_message_processed(chat_id, message_id)
        return

    if not user.get("bot_enabled", True):
        logger.info(
            "Bot is OFF for %s (flow=%s) - ignoring the message. "
            "Use POST /admin/resume/%s to turn it back on.",
            chat_id,
            user.get("flow"),
            chat_id,
        )
        json_store.mark_message_processed(chat_id, message_id)
        return

    step = user.get("step", STEP_NEW)
    logger.info(
        "Handling %r from %s (step=%s, language=%s, flow=%s)",
        reply,
        chat_id,
        step,
        user.get("language"),
        user.get("flow"),
    )

    if step == STEP_NEW:
        await _start_onboarding(chat_id)
    elif step == STEP_AWAITING_LANGUAGE:
        await _handle_language_choice(chat_id, reply)
    elif step == STEP_AWAITING_INTEREST:
        await _handle_interest_choice(chat_id, user.get("language"), reply)
    elif step == STEP_AWAITING_DETAIL:
        await _handle_detail_choice(chat_id, user.get("language"), user.get("flow"), reply)
    else:
        # Onboarding is finished. Never restart it automatically - from here on
        # the business owner answers, and their first manual reply arrives as
        # outgoingMessageReceived and disables the bot for good.
        logger.info("Onboarding already complete for %s - no automatic reply", chat_id)

    json_store.mark_message_processed(chat_id, message_id)


async def handle_webhook(payload: dict[str, Any]) -> None:
    """Route one GREEN-API notification. Unknown types are ignored on purpose."""
    type_webhook = payload.get("typeWebhook")
    chat_id = (payload.get("senderData") or {}).get("chatId")

    if type_webhook == OUTGOING_MANUAL_MESSAGE:
        # Sent by the owner from WhatsApp / Web / Desktop - a human took over.
        if chat_id:
            logger.info("Manual reply detected in %s - switching the bot OFF", chat_id)
            handover_to_human(chat_id)
        else:
            logger.warning("%s webhook without a chatId - ignoring", OUTGOING_MANUAL_MESSAGE)
        return

    if type_webhook == OUTGOING_API_MESSAGE:
        # Our own message, sent through GREEN-API. Never a human takeover.
        logger.info("Our own API message to %s - bot stays ON", chat_id)
        return

    if type_webhook != INCOMING_MESSAGE:
        logger.info("Ignoring webhook type %r (nothing to do)", type_webhook)
        return

    message_id = payload.get("idMessage")
    if not chat_id or not message_id:
        logger.warning(
            "Incoming webhook is missing chatId (%r) or idMessage (%r) - ignoring",
            chat_id,
            message_id,
        )
        return

    message_data = payload.get("messageData") or {}
    reply = extract_reply(message_data)
    if reply is None:
        logger.info(
            "Ignoring %s from %s - the bot only understands text and button replies",
            message_data.get("typeMessage"),
            chat_id,
        )
        return

    if json_store.has_processed_message(chat_id, message_id):
        logger.info("Duplicate notification %s for %s - already answered", message_id, chat_id)
        return

    await handle_incoming_message(chat_id, message_id, reply)
