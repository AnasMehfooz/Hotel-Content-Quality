"""Text helpers for German hotel content (umlauts, phone numbers, URLs)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

_TRANSLIT = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def transliterate(text: str) -> str:
    """German-style ASCII folding: Köln -> Koeln, Straße -> Strasse."""
    folded = text.translate(_TRANSLIT)
    return unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", transliterate(text).lower()).strip("-")


def mojibake(text: str) -> str:
    """Simulate UTF-8 bytes decoded as Windows-1252 (Köln -> KÃ¶ln)."""
    return text.encode("utf-8").decode("cp1252", errors="replace")


def has_non_ascii(text: str | None) -> bool:
    return bool(text) and any(ord(ch) > 127 for ch in text)


_PHONE_STRIP = re.compile(r"[\s/\-.()]")


def normalize_phone_de(raw: str | None) -> str | None:
    """Normalize a German phone number to E.164 (+49...), or None if it is not plausible.

    Handles the formats partners actually send: ``0221 / 123456``, ``+49 (0)221 123456``,
    ``0049 221 123456``. Used to clean the master catalog, not by the partner checks.
    """
    if not raw:
        return None
    first = re.split(r"[;,]", raw)[0]
    first = first.replace("(0)", "")
    digits = _PHONE_STRIP.sub("", first)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+49" + digits[1:]
    if not re.fullmatch(r"\+49[1-9]\d{5,12}", digits):
        return None
    return digits


def split_de_number(e164: str) -> tuple[str, str]:
    """Split +49 numbers into (area code without trunk 0, subscriber) for display formats."""
    national = e164.removeprefix("+49")
    if national[:2] in {"30", "40", "69", "89"}:  # Berlin, Hamburg, Frankfurt, München
        return national[:2], national[2:]
    if national.startswith(("15", "16", "17")):  # mobile prefixes
        return national[:3], national[3:]
    return national[:3], national[3:]


def normalize_url(raw: str | None) -> str | None:
    """Return an https URL with a plausible host, or None."""
    if not raw:
        return None
    value = raw.strip().split(";")[0].strip()
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = "https://" + value
    parts = urlsplit(value)
    host = parts.hostname or ""
    if " " in value or "." not in host or ".." in host or not re.fullmatch(r"[a-z0-9.\-]+", host):
        return None
    return f"https://{host}{parts.path.rstrip('/')}"
