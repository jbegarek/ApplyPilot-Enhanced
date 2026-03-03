"""
Unified LLM client for ApplyPilot.

Uses the Claude Code CLI (`claude -p`) as the LLM backend.
No external API keys needed — runs on the user's Claude Code subscription.

LLM_MODEL env var overrides the Claude model (default: sonnet).
"""

import logging
import os
import shutil
import subprocess
import time

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UsageLimitError(Exception):
    """Raised when Claude CLI reports the user has hit their usage limit.

    Attributes:
        raw_message: The original error text from the CLI.
    """

    def __init__(self, message: str, raw_message: str = "") -> None:
        super().__init__(message)
        self.raw_message = raw_message


# Phrases in CLI stderr/stdout that indicate a usage-limit condition
_USAGE_LIMIT_PHRASES = (
    "you've hit your limit",
    "you have hit your limit",
    "hit your limit",
    "usage limit",
    "rate limit",
    "quota exceeded",
    "too many requests",
    "exceeded your",
    "request limit",
    "capacity",
    "throttled",
    "try again later",
    "overloaded",
)


def _is_usage_limit_error(text: str) -> bool:
    """Return True if *text* looks like a usage/rate-limit error."""
    if not text:
        return False
    lower = text.lower()
    return any(phrase in lower for phrase in _USAGE_LIMIT_PHRASES)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 5
_TIMEOUT = 300  # seconds — tailoring prompts are large and need time

# Base wait on first failure (doubles each retry, caps at 60s).
_RATE_LIMIT_BASE_WAIT = 10


# ---------------------------------------------------------------------------
# Claude CLI Client
# ---------------------------------------------------------------------------

class ClaudeCLIClient:
    """LLM client that uses the Claude Code CLI subprocess.

    Requires `claude` to be installed and authenticated (via Claude Code).
    No API key needed — uses the existing Claude Code session/subscription.
    """

    def __init__(self, model: str = "sonnet") -> None:
        self.model = model

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat request via the Claude CLI and return the response text.

        Converts OpenAI-style messages into a single prompt for `claude -p`.
        """
        # Separate system messages from user/assistant messages.
        # System messages go via --system-prompt; the rest become the user prompt.
        system_parts: list[str] = []
        user_parts: list[str] = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                user_parts.append(content)
            elif role == "assistant":
                user_parts.append(f"PREVIOUS RESPONSE:\n{content}")

        prompt = "\n\n---\n\n".join(user_parts)
        system_prompt = "\n\n".join(system_parts) if system_parts else None

        # Strip CLAUDECODE env var to allow subprocess invocation from
        # within a running Claude Code session (same pattern as apply/launcher.py)
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        cmd = ["claude", "-p", "--model", self.model]
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        for attempt in range(_MAX_RETRIES):
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_TIMEOUT,
                    env=env,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"

                    # Usage/rate-limit errors should not be retried — bubble up immediately
                    if _is_usage_limit_error(error_msg):
                        raise UsageLimitError(
                            f"Claude API usage limit reached: {error_msg[:300]}",
                            raw_message=error_msg,
                        )

                    if attempt < _MAX_RETRIES - 1:
                        wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)
                        log.warning(
                            "Claude CLI failed (exit %d): %s. Retrying in %ds (%d/%d)",
                            result.returncode, error_msg[:200], wait,
                            attempt + 1, _MAX_RETRIES,
                        )
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Claude CLI failed (exit {result.returncode}): {error_msg[:500]}")

                output = result.stdout.strip()
                if not output:
                    if attempt < _MAX_RETRIES - 1:
                        log.warning("Claude CLI returned empty output, retrying...")
                        time.sleep(5)
                        continue
                    raise RuntimeError("Claude CLI returned empty output")

                return output

            except subprocess.TimeoutExpired:
                if attempt < _MAX_RETRIES - 1:
                    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)
                    log.warning(
                        "Claude CLI timed out, retrying in %ds (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise

        raise RuntimeError("Claude CLI failed after all retries")

    def ask(self, prompt: str, **kwargs) -> str:
        """Convenience: single user prompt -> assistant response."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        pass  # No persistent connection to clean up


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: ClaudeCLIClient | None = None


def get_client() -> ClaudeCLIClient:
    """Return (or create) the module-level ClaudeCLIClient singleton.

    Requires the `claude` CLI to be on PATH (installed via Claude Code).
    """
    global _instance
    if _instance is None:
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude Code CLI not found on PATH. "
                "Install from https://claude.ai/code"
            )
        model = os.environ.get("LLM_MODEL", "sonnet")
        log.info("LLM provider: Claude CLI  model: %s", model)
        _instance = ClaudeCLIClient(model)
    return _instance
