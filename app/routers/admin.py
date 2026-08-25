"""Admin endpoints, protected by the X-Admin-Key header."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.storage import json_store

router = APIRouter(prefix="/admin", tags=["admin"])


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
