"""All HTTP communication with GREEN-API lives here.

Request format (https://green-api.com/en/docs/request-format/):
    {apiUrl}/waInstance{idInstance}/{method}/{apiTokenInstance}

sendMessage (https://green-api.com/en/docs/api/sending/SendMessage/):
    POST body {"chatId": "<id>@c.us", "message": "..."}
    response  {"idMessage": "3EB0C767D097B7C7C030"}

sendInteractiveButtons (https://green-api.com/en/docs/api/sending/SendInteractiveButtons/):
    POST body {"chatId": ..., "header": ..., "body": ..., "footer": ...,
               "buttons": [{"type": "reply", "buttonId": "1", "buttonText": "..."}]}
    response  {"idMessage": ...}
    Limits: at most 3 buttons, buttonText at most 25 characters.
    GREEN-API marks this method as beta, so callers must handle GreenAPIError.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GreenAPIError(RuntimeError):
    """Raised when GREEN-API could not be reached or rejected the request."""


def _method_url(method: str) -> str:
    """Build the endpoint URL. The token is part of the path - never log this."""
    base = settings.green_api_api_url.rstrip("/")
    return f"{base}/waInstance{settings.green_api_instance_id}/{method}/{settings.green_api_token}"


def _safe_label(method: str) -> str:
    """A loggable description of a call that contains no credentials."""
    return f"GREEN-API {method} (instance {settings.green_api_instance_id})"


async def _post(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    label = _safe_label(method)
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.post(_method_url(method), json=payload)
    except httpx.HTTPError as exc:
        # str(exc) can contain the request URL, which embeds the token.
        logger.error("%s failed: %s", label, type(exc).__name__)
        raise GreenAPIError(f"{label} request failed") from exc

    if response.status_code >= 400:
        logger.error("%s returned HTTP %s", label, response.status_code)
        raise GreenAPIError(f"{label} returned HTTP {response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        logger.error("%s returned a non-JSON body", label)
        raise GreenAPIError(f"{label} returned a non-JSON body") from exc

    if not isinstance(body, dict):
        logger.error("%s returned an unexpected JSON shape", label)
        raise GreenAPIError(f"{label} returned an unexpected JSON shape")

    return body


async def send_text(chat_id: str, message: str) -> dict[str, Any]:
    """Send a plain text WhatsApp message. Returns the GREEN-API response."""
    body = await _post("sendMessage", {"chatId": chat_id, "message": message})

    if not body.get("idMessage"):
        logger.error("%s response has no idMessage", _safe_label("sendMessage"))
        raise GreenAPIError("sendMessage response has no idMessage")

    logger.info("Sent message %s to %s", body["idMessage"], chat_id)
    return body


# GREEN-API limits for sendInteractiveButtons.
MAX_BUTTONS = 3
MAX_BUTTON_TEXT_LENGTH = 25


async def send_buttons(
    chat_id: str,
    body: str,
    buttons: list[dict[str, Any]],
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Send an interactive button menu.

    Raises GreenAPIError if the menu breaks a documented limit or if GREEN-API
    rejects the call - callers are expected to fall back to a plain text menu.
    """
    if not 1 <= len(buttons) <= MAX_BUTTONS:
        raise GreenAPIError(f"sendInteractiveButtons allows 1-{MAX_BUTTONS} buttons")
    for button in buttons:
        if len(button.get("buttonText", "")) > MAX_BUTTON_TEXT_LENGTH:
            raise GreenAPIError(
                f"buttonText longer than {MAX_BUTTON_TEXT_LENGTH} characters: "
                f"{button.get('buttonId')}"
            )

    payload: dict[str, Any] = {"chatId": chat_id, "body": body, "buttons": buttons}
    if header:
        payload["header"] = header
    if footer:
        payload["footer"] = footer

    response = await _post("sendInteractiveButtons", payload)

    if not response.get("idMessage"):
        logger.error("%s response has no idMessage", _safe_label("sendInteractiveButtons"))
        raise GreenAPIError("sendInteractiveButtons response has no idMessage")

    logger.info("Sent button menu %s to %s", response["idMessage"], chat_id)
    return response
