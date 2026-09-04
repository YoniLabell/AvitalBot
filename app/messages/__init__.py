"""Message catalogue lookup by language code."""

from typing import Any

from app.messages import en, he

_CATALOGUES = {"he": he, "en": en}

DEFAULT_LANGUAGE = "he"


def catalogue(language: str | None):
    """Return the message module for a language, falling back to the default."""
    return _CATALOGUES.get(language or "", _CATALOGUES[DEFAULT_LANGUAGE])


def menu_as_text(
    body: str, buttons: list[dict[str, Any]], footer: str | None = None
) -> str:
    """Render a button menu as a numbered plain-text message.

    Used when GREEN-API cannot deliver interactive buttons, so the wording only
    ever has to be maintained once, in the catalogue above.
    """
    lines = [body, ""]
    lines += [f"{button['buttonId']}. {button['buttonText']}" for button in buttons]
    if footer:
        lines += ["", footer]
    return "\n".join(lines)
