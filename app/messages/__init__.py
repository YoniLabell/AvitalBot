"""Message catalogue lookup by language code."""

from app.messages import en, he

_CATALOGUES = {"he": he, "en": en}

DEFAULT_LANGUAGE = "he"


def catalogue(language: str | None):
    """Return the message module for a language, falling back to the default."""
    return _CATALOGUES.get(language or "", _CATALOGUES[DEFAULT_LANGUAGE])
