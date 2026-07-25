"""
PII redaction and preview truncation.

Applied in the SDK, before anything leaves the process — the point being that
sensitive values never reach the network, so the ingestion service can't leak what
it was never sent.

This is pattern matching, not a guarantee. It catches the common structured
identifiers; it will not catch a name, an address, or a secret in prose. Treat it
as reducing exposure, not eliminating it.
"""

import re

PLACEHOLDER = "[REDACTED]"

# Ordered: more specific patterns first, so an email inside a longer string isn't
# partially consumed by a looser rule.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    # Common provider key shapes (OpenAI, Anthropic, GitHub, Slack).
    ("api_key", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    # 13-19 digits with optional separators, which covers card numbers. Checked
    # before the generic long-number rule.
    ("card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    # Deliberately loose: +CC then 9-14 digits with separators.
    ("phone", re.compile(r"\+\d{1,3}[\s.-]?(?:\(?\d{1,4}\)?[\s.-]?){2,5}\d{2,4}")),
]


def redact(text: str, *, patterns: list[tuple[str, re.Pattern[str]]] | None = None) -> str:
    """Replace every recognised identifier with a placeholder."""
    if not text:
        return text

    for _name, pattern in patterns or PATTERNS:
        text = pattern.sub(PLACEHOLDER, text)
    return text


def make_preview(text: str, *, limit: int = 500, redact_pii: bool = True) -> str:
    """
    Redact, then truncate to `limit` characters.

    Redaction runs *before* truncation. The other order can cut a pattern in half
    and leave a recognisable fragment behind — half a card number is still a
    disclosure.
    """
    if not text:
        return ""

    if redact_pii:
        text = redact(text)

    text = " ".join(text.split())

    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def preview_messages(
    messages: list[dict[str, object]],
    *,
    limit: int = 500,
    redact_pii: bool = True,
) -> str:
    """
    Collapse a chat message list into one preview string.

    Renders as `role: content` lines from the end of the conversation backwards,
    because the most recent turn is the one worth seeing when debugging.
    """
    if not messages:
        return ""

    rendered: list[str] = []
    for message in reversed(messages):
        role = str(message.get("role", "?"))
        content = message.get("content")

        # Multimodal content arrives as a list of parts; keep only the text ones.
        if isinstance(content, list):
            content = " ".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )

        rendered.append(f"{role}: {content}")

        if sum(len(line) for line in rendered) > limit * 2:
            break

    joined = " | ".join(reversed(rendered))
    return make_preview(joined, limit=limit, redact_pii=redact_pii)
