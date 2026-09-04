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

sendFileByUpload (https://green-api.com/en/docs/api/sending/SendFileByUpload/):
    POST multipart to the MEDIA host, not the API host:
        {mediaUrl}/waInstance{idInstance}/sendFileByUpload/{apiTokenInstance}
    fields chatId, file, fileName and optionally caption
    response {"idMessage": ..., "urlFile": ...}

The API token is part of the URL path, so everything logged from this module
goes through _redact() first.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# GREEN-API limits for sendInteractiveButtons.
MAX_BUTTONS = 3
MAX_BUTTON_TEXT_LENGTH = 25

# How much of a GREEN-API response body to put in the log.
MAX_LOGGED_BODY = 500


class GreenAPIError(RuntimeError):
    """Raised when GREEN-API could not be reached or rejected the request."""


# A token shorter than this is not a real GREEN-API token, and blindly
# replacing it would shred unrelated words in the log ("Connection" -> "Connec***").
MIN_REDACTABLE_TOKEN_LENGTH = 8


def _redact(text: str) -> str:
    """Replace the API token wherever it appears, so URLs are safe to log."""
    token = settings.green_api_token
    if token and len(token) >= MIN_REDACTABLE_TOKEN_LENGTH:
        text = text.replace(token, "***TOKEN***")
    return text


def _method_url(method: str, media: bool = False) -> str:
    base = settings.green_api_media_url if media else settings.green_api_api_url
    base = base.rstrip("/")
    return f"{base}/waInstance{settings.green_api_instance_id}/{method}/{settings.green_api_token}"


def _safe_url(method: str) -> str:
    """The endpoint URL with the token masked - safe to log."""
    return _redact(_method_url(method))


MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # GREEN-API's documented file size limit.


def _check_configured(method: str) -> None:
    """Fail loudly and specifically rather than with an obscure URL error."""
    missing = [
        name
        for name, value in (
            ("GREEN_API_INSTANCE_ID", settings.green_api_instance_id),
            ("GREEN_API_TOKEN", settings.green_api_token),
            ("GREEN_API_API_URL", settings.green_api_api_url),
        )
        if not value
    ]
    if missing:
        message = (
            f"Cannot call GREEN-API {method}: {', '.join(missing)} not set. "
            "Set them in .env locally, or in the Render service Environment tab."
        )
        logger.error(message)
        raise GreenAPIError(message)


async def _request(
    method: str,
    payload: dict[str, Any] | None = None,
    *,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    media: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Call one GREEN-API method.

    POST with JSON when there is a payload, POST multipart when there are
    files, GET otherwise. Uploads go to the media host (media=True).
    """
    _check_configured(method)

    url = _method_url(method, media=media)
    safe_url = _redact(url)
    verb = "GET" if payload is None and files is None else "POST"
    logger.info("GREEN-API -> %s %s", verb, safe_url)
    if payload is not None:
        logger.debug("GREEN-API request body: %s", payload)
    if data is not None:
        logger.debug("GREEN-API form fields: %s", data)

    try:
        async with httpx.AsyncClient(timeout=timeout or settings.http_timeout_seconds) as client:
            if files is not None:
                response = await client.post(url, data=data, files=files)
            elif payload is not None:
                response = await client.post(url, json=payload)
            else:
                response = await client.get(url)
    except httpx.HTTPError as exc:
        # The exception text can contain the request URL, which embeds the token.
        detail = _redact(f"{type(exc).__name__}: {exc}")
        logger.error("GREEN-API %s could not be reached - %s", method, detail)
        if isinstance(exc, httpx.UnsupportedProtocol):
            logger.error(
                "%s looks wrong (%r). It must be a full URL, for example %s",
                "GREEN_API_MEDIA_URL" if media else "GREEN_API_API_URL",
                settings.green_api_media_url if media else settings.green_api_api_url,
                "https://media.green-api.com" if media else "https://api.green-api.com",
            )
        elif isinstance(exc, httpx.TimeoutException):
            logger.error(
                "GREEN-API did not answer within %.1fs (HTTP_TIMEOUT_SECONDS)",
                settings.http_timeout_seconds,
            )
        raise GreenAPIError(f"GREEN-API {method} could not be reached - {detail}") from exc

    body_text = _redact(response.text)[:MAX_LOGGED_BODY]

    if response.status_code >= 400:
        logger.error(
            "GREEN-API %s returned HTTP %s: %s", method, response.status_code, body_text
        )
        logger.error("Hint: %s", _http_error_hint(response.status_code))
        raise GreenAPIError(
            f"GREEN-API {method} returned HTTP {response.status_code}: {body_text}"
        )

    try:
        parsed = response.json()
    except ValueError as exc:
        logger.error("GREEN-API %s returned a non-JSON body: %s", method, body_text)
        raise GreenAPIError(f"GREEN-API {method} returned a non-JSON body") from exc

    if not isinstance(parsed, dict):
        logger.error("GREEN-API %s returned %s, expected an object: %s", method, type(parsed).__name__, body_text)
        raise GreenAPIError(f"GREEN-API {method} returned an unexpected JSON shape")

    logger.debug("GREEN-API %s response: %s", method, body_text)
    return parsed


def _http_error_hint(status_code: int) -> str:
    """Plain-language guidance for the statuses GREEN-API actually returns."""
    return {
        400: "Bad request - check the payload; sendInteractiveButtons is beta and "
             "some instances reject it.",
        401: "Unauthorized - GREEN_API_TOKEN is wrong for this instance.",
        403: "Forbidden - the instance may be blocked, expired, or on a plan that "
             "does not allow this method.",
        404: "Not found - GREEN_API_INSTANCE_ID or GREEN_API_API_URL is wrong.",
        429: "Rate limited - too many requests to GREEN-API.",
        466: "Quota exceeded - the GREEN-API instance has run out of its message quota.",
    }.get(status_code, "See https://green-api.com/en/docs/api/ for this status code.")


def _require_id_message(method: str, response: dict[str, Any], chat_id: str) -> str:
    id_message = response.get("idMessage")
    if not id_message:
        logger.error("GREEN-API %s to %s returned no idMessage: %s", method, chat_id, response)
        raise GreenAPIError(f"GREEN-API {method} response has no idMessage")
    return id_message


async def send_text(chat_id: str, message: str) -> dict[str, Any]:
    """Send a plain text WhatsApp message. Returns the GREEN-API response."""
    logger.info("Sending text to %s (%d chars)", chat_id, len(message))
    response = await _request("sendMessage", {"chatId": chat_id, "message": message})
    id_message = _require_id_message("sendMessage", response, chat_id)
    logger.info("Sent text %s to %s", id_message, chat_id)
    return response


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
        raise GreenAPIError(
            f"sendInteractiveButtons allows 1-{MAX_BUTTONS} buttons, got {len(buttons)}"
        )
    for button in buttons:
        text = button.get("buttonText", "")
        if len(text) > MAX_BUTTON_TEXT_LENGTH:
            raise GreenAPIError(
                f"buttonText {text!r} is {len(text)} characters, "
                f"the limit is {MAX_BUTTON_TEXT_LENGTH}"
            )

    payload: dict[str, Any] = {"chatId": chat_id, "body": body, "buttons": buttons}
    if header:
        payload["header"] = header
    if footer:
        payload["footer"] = footer

    labels = [button.get("buttonText") for button in buttons]
    logger.info("Sending %d buttons to %s: %s", len(buttons), chat_id, labels)
    response = await _request("sendInteractiveButtons", payload)
    id_message = _require_id_message("sendInteractiveButtons", response, chat_id)
    logger.info("Sent button menu %s to %s", id_message, chat_id)
    return response


async def get_state_instance() -> dict[str, Any]:
    """Authorization state of the instance, e.g. {"stateInstance": "authorized"}."""
    return await _request("getStateInstance")


async def get_settings() -> dict[str, Any]:
    """Instance settings, including webhookUrl and the webhook on/off flags."""
    return await _request("getSettings")


async def send_file(chat_id: str, file_path: str | Path, caption: str | None = None) -> dict[str, Any]:
    """Upload a local file and send it. Used for the class schedule image."""
    path = Path(file_path)

    if not path.is_file():
        message = f"Cannot send {path} to {chat_id}: the file does not exist"
        logger.error(message)
        raise GreenAPIError(message)

    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise GreenAPIError(f"{path.name} is {size} bytes, over GREEN-API's 100 MB limit")

    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    logger.info(
        "Sending file %s (%s, %d bytes) to %s", path.name, content_type, size, chat_id
    )

    data: dict[str, Any] = {"chatId": chat_id, "fileName": path.name}
    if caption:
        data["caption"] = caption

    response = await _request(
        "sendFileByUpload",
        data=data,
        files={"file": (path.name, path.read_bytes(), content_type)},
        media=True,
        timeout=settings.upload_timeout_seconds,
    )

    id_message = _require_id_message("sendFileByUpload", response, chat_id)
    logger.info("Sent file %s as %s to %s", path.name, id_message, chat_id)
    return response
