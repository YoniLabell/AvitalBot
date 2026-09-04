"""Admin endpoints, protected by the X-Admin-Key header."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.services import bot, green_api
from app.storage import json_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# GREEN-API instance settings the bot depends on (GetSettings field -> why).
REQUIRED_WEBHOOK_SETTINGS = {
    "incomingWebhook": "receive customer messages",
    "outgoingMessageWebhook": "detect a manual reply and switch the bot off",
    "outgoingAPIMessageWebhook": "recognise the bot's own messages",
}


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY is not configured",
        )
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )


@router.get("/user/{chat_id}", dependencies=[Depends(require_admin_key)])
async def read_user(chat_id: str) -> dict[str, Any]:
    user = json_store.get_user(chat_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown chat_id")
    return {"chat_id": chat_id, "user": user}


@router.post("/pause/{chat_id}", dependencies=[Depends(require_admin_key)])
async def pause(chat_id: str) -> dict[str, Any]:
    return {"chat_id": chat_id, "user": json_store.pause_user(chat_id)}


@router.post("/resume/{chat_id}", dependencies=[Depends(require_admin_key)])
async def resume(chat_id: str) -> dict[str, Any]:
    return {"chat_id": chat_id, "user": json_store.resume_user(chat_id)}


@router.post("/reset/{chat_id}", dependencies=[Depends(require_admin_key)])
async def reset(chat_id: str) -> dict[str, Any]:
    json_store.reset_user(chat_id)
    return {"chat_id": chat_id, "status": "reset"}


@router.get("/diagnostics", dependencies=[Depends(require_admin_key)])
async def diagnostics() -> dict[str, Any]:
    """Check the whole setup and say, in plain words, what is wrong.

    This is the endpoint to call first when the bot is not answering. It does
    contact GREEN-API (unlike /health), so it is admin-only.
    """
    problems: list[str] = list(settings.configuration_problems())
    report: dict[str, Any] = {
        "config": {
            "green_api_api_url": settings.green_api_api_url,
            "green_api_instance_id": settings.green_api_instance_id or None,
            "green_api_token_set": bool(settings.green_api_token),
            "admin_api_key_set": bool(settings.admin_api_key),
            "green_api_media_url": settings.green_api_media_url,
            "data_file_path": settings.data_file_path,
            "assets_dir": settings.assets_dir,
            "log_level": settings.log_level,
        },
        "storage": _storage_report(),
    }

    for missing in bot.missing_answer_images():
        problems.append(f"An image the bot sends is not on disk - {missing}")

    report["instance_state"] = await _instance_state(problems)
    report["instance_settings"] = await _instance_settings(problems)

    report["problems"] = problems
    report["status"] = "ok" if not problems else "problems_found"
    logger.info("Diagnostics run: %s problem(s) found", len(problems))
    return report


def _storage_report() -> dict[str, Any]:
    try:
        users = json_store.all_users()
    except Exception as exc:  # pragma: no cover - defensive
        return {"readable": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"readable": True, "known_customers": len(users)}


async def _instance_state(problems: list[str]) -> dict[str, Any]:
    try:
        state = await green_api.get_state_instance()
    except green_api.GreenAPIError as exc:
        problems.append(f"Could not read the GREEN-API instance state: {exc}")
        return {"error": str(exc)}

    if state.get("stateInstance") != "authorized":
        problems.append(
            f"GREEN-API instance state is {state.get('stateInstance')!r}, expected 'authorized'. "
            "Scan the QR code again in the GREEN-API console."
        )
    return state


async def _instance_settings(problems: list[str]) -> dict[str, Any]:
    try:
        instance_settings = await green_api.get_settings()
    except green_api.GreenAPIError as exc:
        problems.append(f"Could not read the GREEN-API instance settings: {exc}")
        return {"error": str(exc)}

    webhook_url = instance_settings.get("webhookUrl") or ""
    if not webhook_url:
        problems.append(
            "No webhookUrl is set on the GREEN-API instance, so no notification will "
            "ever reach this service. Set it to https://<your-service>/webhook/green-api"
        )
    elif not webhook_url.rstrip("/").endswith("/webhook/green-api"):
        problems.append(
            f"The instance webhookUrl is {webhook_url!r}, which does not end in "
            "/webhook/green-api - notifications are going somewhere else."
        )

    for field, reason in REQUIRED_WEBHOOK_SETTINGS.items():
        if instance_settings.get(field) != "yes":
            problems.append(
                f"GREEN-API setting {field} is {instance_settings.get(field)!r}, expected 'yes' "
                f"- needed to {reason}."
            )

    return {
        "webhookUrl": webhook_url or None,
        # webhookUrlToken is a shared secret; report only whether one is set.
        "webhookUrlTokenSet": bool(instance_settings.get("webhookUrlToken")),
        **{field: instance_settings.get(field) for field in REQUIRED_WEBHOOK_SETTINGS},
        "stateWebhook": instance_settings.get("stateWebhook"),
    }
