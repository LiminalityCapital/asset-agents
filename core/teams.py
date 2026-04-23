"""Post alerts to Teams via a Power Automate webhook workflow."""

import json
import os
import urllib.error
import urllib.request


class TeamsError(RuntimeError):
    pass


def _build_card(
    message: str,
    *,
    title: str | None,
    facts: dict[str, str] | None,
    footer: str | None,
    link: tuple[str, str] | None,
) -> dict:
    body: list[dict] = []

    if title:
        body.append({
            "type": "TextBlock",
            "text": title,
            "size": "Large",
            "weight": "Bolder",
            "color": "Accent",
            "wrap": True,
        })

    if facts:
        body.append({
            "type": "FactSet",
            "facts": [{"title": k, "value": v} for k, v in facts.items()],
            "spacing": "Small",
        })

    body.append({
        "type": "TextBlock",
        "text": message,
        "wrap": True,
        "separator": bool(title or facts),
        "spacing": "Medium",
    })

    if footer:
        body.append({
            "type": "TextBlock",
            "text": footer,
            "size": "Small",
            "isSubtle": True,
            "wrap": True,
            "spacing": "Medium",
        })

    card: dict = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    if link:
        label, url = link
        card["actions"] = [{"type": "Action.OpenUrl", "title": label, "url": url}]

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


def send(
    message: str,
    *,
    title: str | None = None,
    facts: dict[str, str] | None = None,
    footer: str | None = None,
    link: tuple[str, str] | None = None,
    timeout: float = 10.0,
) -> None:
    """POST an Adaptive Card to TEAMS_WEBHOOK_URL. Raises TeamsError on failure."""
    url = os.getenv("TEAMS_WEBHOOK_URL")
    if not url:
        raise TeamsError("TEAMS_WEBHOOK_URL is not set")
    if not message:
        raise TeamsError("message is empty")

    payload = _build_card(message, title=title, facts=facts, footer=footer, link=link)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                raise TeamsError(f"webhook returned HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise TeamsError(f"webhook returned HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise TeamsError(f"webhook request failed: {e.reason}") from e
