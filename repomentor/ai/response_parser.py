"""Turn whatever the model returned into validated Python objects.

Models (especially small local ones) wrap JSON in code fences, add a sentence
before it, leave trailing commas or use Turkish enum values. This module is
forgiving on input and strict on output.
"""

from __future__ import annotations

import json
import re

from repomentor.models.issue import Issue, Location

SEVERITY_ALIASES = {
    "critical": "high", "kritik": "high", "high": "high", "yüksek": "high", "yuksek": "high",
    "medium": "medium", "orta": "medium", "moderate": "medium",
    "low": "low", "düşük": "low", "dusuk": "low", "minor": "low", "info": "low",
}
CATEGORY_ALIASES = {
    "security": "security", "güvenlik": "security",
    "quality": "quality", "code quality": "quality", "kalite": "quality", "kod kalitesi": "quality", "readability": "quality", "architecture": "organization",
    "testing": "testing", "test": "testing", "tests": "testing",
    "documentation": "documentation", "dokümantasyon": "documentation", "readme": "documentation", "docs": "documentation",
    "organization": "organization", "organizasyon": "organization", "mimari": "organization", "structure": "organization",
    "runnable": "runnable", "çalıştırılabilirlik": "runnable", "deployment": "runnable", "configuration": "runnable",
}


class ParseError(ValueError):
    pass


def extract_json(text: str) -> dict:
    """Find and decode the first JSON object in `text`."""
    if not text or not text.strip():
        raise ParseError("Model boş yanıt döndürdü.")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    for candidate in (cleaned, _outer_object(cleaned)):
        if not candidate:
            continue
        for attempt in (candidate, _repair(candidate)):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    raise ParseError("Model yanıtı geçerli JSON değil.")


def _outer_object(text: str) -> str | None:
    """Slice from the first '{' to its matching '}' (string-aware)."""
    start = text.find("{")
    if start < 0:
        return None
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]  # truncated output; _repair may still save it


def _repair(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Close brackets of a truncated response.
    opens = text.count("{") - text.count("}")
    arrays = text.count("[") - text.count("]")
    if text.count('"') % 2:
        text += '"'
    return text + "]" * max(arrays, 0) + "}" * max(opens, 0)


def _text(value, limit: int = 2500) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    return str(value).strip()[:limit]


def _string_list(value, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        value = [line.strip(" -•*\t") for line in value.splitlines()]
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("text") or item.get("title") or " ".join(str(v) for v in item.values())
        item = _text(item, 500).lstrip("-•* ").strip()
        if item:
            items.append(item)
    return items[:limit]


def _match_path(raw: str, known_paths: set[str]) -> str | None:
    """Accept a file only if it exists in the project (no hallucinated paths)."""
    raw = (raw or "").strip().strip("`'\"").removeprefix("./").split(":")[0]
    if not raw:
        return None
    if raw in known_paths:
        return raw
    suffix_hits = [p for p in known_paths if p.endswith("/" + raw)]
    return suffix_hits[0] if len(suffix_hits) == 1 else None


def _minutes(raw: dict) -> int:
    """Effort from `estimated_minutes`, or from a free-text `estimated_effort` such as '2 saat'."""
    text = str(raw.get("estimated_minutes") or raw.get("estimated_effort") or "30")
    match = re.search(r"\d+", text)
    minutes = int(match.group()) if match else 30
    if any(unit in text.lower() for unit in ("saat", "hour")):
        minutes *= 60
    return max(5, min(minutes, 480))


def _parse_issue(raw: dict, index: int, known_paths: set[str]) -> Issue | None:
    title = _text(raw.get("title"), 160)
    recommendation = _text(raw.get("recommendation") or raw.get("fix") or raw.get("suggestion"), 800)
    if not title or not recommendation:
        return None
    path = _match_path(_text(raw.get("file")), known_paths)
    return Issue(
        rule_id=f"AI-{index:02d}", title=title,
        severity=SEVERITY_ALIASES.get(_text(raw.get("severity")).lower(), "low"),
        category=CATEGORY_ALIASES.get(_text(raw.get("category")).lower(), "quality"),
        explanation=_text(raw.get("explanation") or raw.get("why"), 800) or "Yapay zekâ değerlendirmesi.",
        recommendation=recommendation, effort_minutes=_minutes(raw),
        locations=[Location(path)] if path else [], source="ai", confidence="low",
    )


def parse_issues(value, known_paths: set[str], limit: int = 6) -> list[Issue]:
    """Validated AI issues; malformed entries are dropped, unknown files removed."""
    if not isinstance(value, list):
        return []
    parsed = (_parse_issue(raw, index, known_paths) for index, raw in enumerate(value[:limit], 1) if isinstance(raw, dict))
    return [issue for issue in parsed if issue is not None]


def normalise_response(data: dict, known_paths: set[str]) -> dict:
    return {
        "summary": _text(data.get("summary"), 1500),
        "architecture_review": _text(data.get("architecture_review") or data.get("architecture"), 2000),
        "readability_review": _text(data.get("readability_review") or data.get("readability"), 1500),
        "strengths": _string_list(data.get("strengths"), 6),
        "issues": parse_issues(data.get("issues"), known_paths),
        "readme_suggestions": _string_list(data.get("readme_suggestions"), 6),
        "next_steps": _string_list(data.get("next_steps"), 8),
        "cv_bullets": _string_list(data.get("cv_bullets"), 5),
        "linkedin_short": _text(data.get("linkedin_short") or data.get("linkedin_description"), 600),
        "linkedin_post": _text(data.get("linkedin_post"), 2500),
    }
