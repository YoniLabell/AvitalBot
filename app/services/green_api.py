"""All HTTP communication with GREEN-API lives here.

Request format (https://green-api.com/en/docs/request-format/):
    {apiUrl}/waInstance{idInstance}/{method}/{apiTokenInstance}

sendMessage (https://green-api.com/en/docs/api/sending/SendMessage/):
    POST body {"chatId": "<id>@c.us", "message": "..."}
    response  {"idMessage": "3EB0C767D097B7C7C030"}
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
