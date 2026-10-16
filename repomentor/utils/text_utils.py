"""Text helpers: secret masking, keyword search and safe decoding."""

from __future__ import annotations

import math
import re

SECRET_ASSIGNMENT = re.compile(
    r"""(?<![A-Za-z0-9_])(?P<name>(?:[A-Za-z_][A-Za-z0-9_]*)?(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIALS?)[A-Za-z0-9_]*)"""
    r"""(?P<sep>\s*[:=]\s*)(?P<quote>['"])(?P<value>[^'"\n]{4,})(?P=quote)""",
    re.IGNORECASE,
)

# Well-known token shapes. Matching one of these is a much stronger signal than a
# variable name, so they are reported with high confidence.
KNOWN_TOKEN_PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS erişim anahtarı": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    "OpenAI API anahtarı": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b"),
    "Anthropic API anahtarı": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b"),
    "Google API anahtarı": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Groq API anahtarı": re.compile(r"\bgsk_[A-Za-z0-9]{40,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "Stripe gizli anahtarı": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b"),
    "Özel anahtar (private key)": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "Veritabanı bağlantı adresi (şifreli)": re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:/'\"]+:[^\s@/'\"]+@"),
}

# Values that are obviously placeholders – reporting these would be noise.
PLACEHOLDER_HINTS = (
    "your", "xxx", "***", "<", "changeme", "change_me", "example", "placeholder",
    "dummy", "todo", "replace", "insert", "here", "none", "null", "secret_key_here",
    "${", "{{", "os.getenv", "os.environ", "getpass",
)


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if len(set(lowered)) <= 2:          # "xxxx", "----", "0000"
        return True
    return any(hint in lowered for hint in PLACEHOLDER_HINTS)


def mask_value(value: str) -> str:
    value = value.strip()
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


def mask_secrets(text: str) -> str:
    """Replace anything that looks like a credential with a masked marker.

    Used before text leaves the machine (LLM prompt) and before it is shown in
    reports, so real keys are never echoed back.
    """
    text = SECRET_ASSIGNMENT.sub(
        lambda m: f"{m.group('name')}{m.group('sep')}{m.group('quote')}***MASKED***{m.group('quote')}",
        text,
    )
    for pattern in KNOWN_TOKEN_PATTERNS.values():
        text = pattern.sub("***MASKED***", text)
    return text


def contains_any(text: str, words: list[str] | tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def decode_bytes(raw: bytes) -> str | None:
    """Decode file content; return None for binary data."""
    if b"\x00" in raw[:4096]:
        return None
    for encoding in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def tr_number(value: float | int | None, digits: int = 1) -> str:
    """Turkish number format: 1.234,5 (dot for thousands, comma for decimals)."""
    if value is None:
        return "-"
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    text = f"{value:,.{digits}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def share_percent(ratio: float) -> str:
    """A share as a percentage that never rounds a gap away: 0.997 → "99,7", not "100"; 0.003 → "0,3", not "0"."""
    value = ratio * 100
    if 99 < value < 100:
        return tr_number(math.floor(value * 10) / 10, 1)
    if 0 < value < 1:
        return tr_number(math.ceil(value * 10) / 10, 1)
    return f"{value:.0f}"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n… (kısaltıldı)"
