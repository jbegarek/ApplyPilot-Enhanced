"""Session state persistence for resume-after-interruption.

Saves the current pipeline command and arguments to a JSON file so the
pipeline can resume from where it left off after a usage-limit pause or
manual interruption.

State file: ~/.applypilot/session.json
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from applypilot.config import APP_DIR

log = logging.getLogger(__name__)

SESSION_PATH = APP_DIR / "session.json"


def save_session(
    command: str,
    args: dict,
    remaining_stages: list[str] | None = None,
    reason: str = "usage_limit",
    reset_at: str | None = None,
) -> Path:
    """Save session state for later resume.

    Args:
        command: CLI command that was running ("run" or "apply").
        args: Dict of CLI arguments to replay on resume.
        remaining_stages: For ``run``, the stages that still need to execute.
        reason: Why the session was saved (usage_limit, interrupted, error).
        reset_at: ISO-8601 timestamp when usage is expected to refresh.

    Returns:
        Path to the saved session file.
    """
    state = {
        "command": command,
        "args": args,
        "remaining_stages": remaining_stages,
        "reason": reason,
        "reset_at": reset_at,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.info("Session saved to %s (reason: %s)", SESSION_PATH, reason)
    return SESSION_PATH


def load_session() -> dict | None:
    """Load saved session state.

    Returns:
        Session dict, or ``None`` if no session file exists.
    """
    if not SESSION_PATH.exists():
        return None
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        log.info("Loaded saved session from %s", SESSION_PATH)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load session file: %s", exc)
        return None


def clear_session() -> None:
    """Remove the saved session file."""
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
        log.info("Cleared saved session.")


def estimate_reset_time(error_message: str) -> str | None:
    """Try to extract or estimate the usage reset time from an error message.

    Claude CLI error messages sometimes include reset info like:
      "Your usage will reset at 2025-06-15T10:00:00Z"
      "Please try again after 3:00 PM UTC"
      "Rate limit resets in 2 hours"

    If no parseable time is found, estimates ~5 hours from now (common
    rolling-window duration for Claude Pro subscriptions).

    Returns:
        ISO-8601 timestamp string, or None if nothing useful can be determined.
    """
    if not error_message:
        return None

    msg_lower = error_message.lower()

    # Pattern 1: explicit ISO timestamp
    iso_match = re.search(r"reset[s ]?\s*(?:at\s+)?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", error_message)
    if iso_match:
        return iso_match.group(1)

    # Pattern 2: "in N hour(s)" / "in N minute(s)"
    hours_match = re.search(r"in\s+(\d+)\s*hour", msg_lower)
    mins_match = re.search(r"in\s+(\d+)\s*min", msg_lower)
    if hours_match:
        delta = timedelta(hours=int(hours_match.group(1)))
        return (datetime.now(timezone.utc) + delta).isoformat()
    if mins_match:
        delta = timedelta(minutes=int(mins_match.group(1)))
        return (datetime.now(timezone.utc) + delta).isoformat()

    # Pattern 3: "resets 9pm (America/New_York)" / "resets at 9:30 PM"
    clock_match = re.search(
        r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b(?:\s*\(([^)]+)\))?",
        error_message,
        flags=re.IGNORECASE,
    )
    if clock_match:
        hour = int(clock_match.group(1))
        minute = int(clock_match.group(2) or 0)
        meridiem = clock_match.group(3).lower()
        tz_name = clock_match.group(4)

        hour = hour % 12
        if meridiem == "pm":
            hour += 12

        tz_info = datetime.now().astimezone().tzinfo
        if tz_name:
            try:
                tz_info = ZoneInfo(tz_name.strip())
            except Exception:
                pass

        now_local = datetime.now(tz_info)
        reset_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if reset_local <= now_local:
            reset_local += timedelta(days=1)
        return reset_local.astimezone(timezone.utc).isoformat()

    # Fallback: estimate 5 hours from now (common Claude Pro rolling window)
    return (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
