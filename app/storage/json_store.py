"""JSON-file backed customer state.

This is the ONLY module that knows where customer state lives. The bot and the
routers talk to it through the functions below, so swapping the JSON file for a
persistent disk (DATA_FILE_PATH=/var/data/users.json) or for a database later
does not require touching any flow logic.

NOTE: on Render Free the filesystem is ephemeral. State is intentionally
temporary in this MVP and is lost on spin-down / restart / redeploy.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Number of recent message ids kept per customer for duplicate detection.
MAX_PROCESSED_MESSAGE_IDS = 100

# Guards read-modify-write cycles inside this process.
_lock = threading.Lock()


def _data_path() -> Path:
    """Resolve the data file path at call time so settings stay overridable."""
    return Path(settings.data_file_path)


def _default_user() -> dict[str, Any]:
    return {
        "language": None,
        "flow": None,
        "step": 0,
        "bot_enabled": True,
        "processed_message_ids": [],
    }


def _read_all() -> dict[str, dict[str, Any]]:
    path = _data_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        logger.exception("Corrupt JSON in %s - starting from an empty store", path)
        return {}
    except OSError:
        logger.exception("Could not read %s - starting from an empty store", path)
        return {}

    if not isinstance(data, dict):
        logger.error("Unexpected JSON shape in %s - starting from an empty store", path)
        return {}
    return data


def _write_all(data: dict[str, dict[str, Any]]) -> None:
    """Write the whole store atomically (temp file in the same dir + rename)."""
    path = _data_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name,
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except OSError:
        logger.exception("Could not write %s", path)
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def init_storage() -> None:
    """Create the data directory and file if they do not exist yet."""
    with _lock:
        if not _data_path().exists():
            _write_all({})


def all_users() -> dict[str, dict[str, Any]]:
    """Every stored customer. Used by the diagnostics endpoint."""
    with _lock:
        return _read_all()


def get_user(chat_id: str) -> dict[str, Any] | None:
    with _lock:
        return _read_all().get(chat_id)


def create_user(chat_id: str) -> dict[str, Any]:
    with _lock:
        data = _read_all()
        user = _default_user()
        data[chat_id] = user
        _write_all(data)
        return dict(user)


def update_user(chat_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge ``updates`` into the customer's record, creating it if needed."""
    with _lock:
        data = _read_all()
        user = data.get(chat_id) or _default_user()
        user.update(updates)
        data[chat_id] = user
        _write_all(data)
        return dict(user)


def pause_user(chat_id: str) -> dict[str, Any]:
    return update_user(chat_id, {"bot_enabled": False})


def resume_user(chat_id: str) -> dict[str, Any]:
    return update_user(chat_id, {"bot_enabled": True})


def reset_user(chat_id: str) -> dict[str, Any]:
    """Forget everything about a customer so onboarding starts again."""
    with _lock:
        data = _read_all()
        data.pop(chat_id, None)
        _write_all(data)
    return _default_user()


def has_processed_message(chat_id: str, message_id: str) -> bool:
    with _lock:
        user = _read_all().get(chat_id)
        if not user:
            return False
        return message_id in user.get("processed_message_ids", [])


def mark_message_processed(chat_id: str, message_id: str) -> None:
    """Record a message id, keeping only the most recent ones."""
    with _lock:
        data = _read_all()
        user = data.get(chat_id) or _default_user()
        seen = [mid for mid in user.get("processed_message_ids", []) if mid != message_id]
        seen.append(message_id)
        user["processed_message_ids"] = seen[-MAX_PROCESSED_MESSAGE_IDS:]
        data[chat_id] = user
        _write_all(data)
