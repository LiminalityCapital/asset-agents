"""Pre-create a Bagel chat session seeded with a follow-up question.

The agent impersonates a user (via X-Authenticated-User) so the created session
is stored under that user's blob prefix. When the same human clicks the link,
Bagel's identity flow resolves them to the same user_id and the session loads.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class BagelError(RuntimeError):
    pass


def _post(path: str, body: dict | None, *, timeout: float) -> dict:
    base = os.getenv("BAGEL_CHAT_URL", "").rstrip("/")
    user_id = os.getenv("BAGEL_USER_ID", "").strip()
    if not base:
        raise BagelError("BAGEL_CHAT_URL is not set")
    if not user_id:
        raise BagelError("BAGEL_USER_ID is not set")

    data = json.dumps(body).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Authenticated-User": user_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                raise BagelError(f"{path} returned HTTP {resp.status}")
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise BagelError(f"{path} returned HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise BagelError(f"{path} request failed: {e.reason}") from e


def precreate_session(question: str, *, wait_timeout: float = 90.0) -> str:
    """Create a session and post `question` as its first message. Returns session_id.

    Uses wait=true on send so the answer is fully generated before we return,
    meaning the user lands on a session that already has Q and A rendered.
    """
    if not question or not question.strip():
        raise BagelError("question is empty")

    new_resp = _post("/api/chat/new", None, timeout=10.0)
    session_id = new_resp.get("session_id")
    if not session_id:
        raise BagelError("new session response missing session_id")

    _post(
        "/api/chat/send?wait=true",
        {"session_id": session_id, "message": question},
        timeout=wait_timeout,
    )
    return session_id
