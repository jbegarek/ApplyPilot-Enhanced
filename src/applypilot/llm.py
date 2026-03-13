"""
Unified LLM client for ApplyPilot.

Selects provider via LLM_PROVIDER env var (default: claude):
  claude  — Claude Code CLI subprocess; no API key needed
  gemini  — Gemini CLI (preferred) or Gemini API fallback
  openai  — OpenAI API; requires OPENAI_API_KEY
  codex   — Codex CLI (preferred) or OpenAI API fallback

LLM_MODEL overrides the default model for the general tier.
LLM_MODEL_GENERAL / LLM_MODEL_TAILOR override per-tier models.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider defaults
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "claude": {"general": "sonnet",           "tailor": "claude-opus-4-6"},
    "gemini": {"general": "gemini-2.5-flash-lite", "tailor": "gemini-2.5-pro"},
    "openai": {"general": "gpt-4o-mini",      "tailor": "gpt-4o"},
    "codex":  {"general": "auto",             "tailor": "auto"},
}


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "claude").lower()


def _is_provider_default_override(model: str | None) -> bool:
    if model is None:
        return True
    return model.strip().lower() in {"", "auto", "default", "cli-default", "provider-default"}


def _model(tier: str = "general") -> str:
    """Return the model name for the current provider and tier.

    Resolution order:
      1. LLM_MODEL_GENERAL / LLM_MODEL_TAILOR (per-tier override)
      2. LLM_MODEL (general-tier override only, tailor is unaffected)
      3. Provider defaults
    """
    prov = _provider()
    defaults = _PROVIDER_DEFAULTS.get(prov, _PROVIDER_DEFAULTS["claude"])

    # 1. Per-tier env var (highest priority)
    tier_env = f"LLM_MODEL_{tier.upper()}"
    tier_override = (os.environ.get(tier_env) or "").strip()
    if tier_override and not _is_provider_default_override(tier_override):
        return tier_override

    # 2. LLM_MODEL applies to general tier only (keeps tailor on its own default)
    override = (os.environ.get("LLM_MODEL") or "").strip()
    if override and tier == "general":
        if _is_provider_default_override(override):
            return defaults[tier]
        # Ignore stale provider-specific defaults (e.g. sonnet) after --llm switches.
        for other_provider, other_defaults in _PROVIDER_DEFAULTS.items():
            if other_provider == prov:
                continue
            if override in other_defaults.values():
                log.warning(
                    "Ignoring LLM_MODEL='%s' for provider '%s'; using %s default.",
                    override,
                    prov,
                    tier,
                )
                break
        else:
            return override

    return defaults[tier]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UsageLimitError(Exception):
    """Raised when the LLM provider reports a usage/rate-limit condition."""

    def __init__(self, message: str, raw_message: str = "") -> None:
        super().__init__(message)
        self.raw_message = raw_message


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
    "resource_exhausted",
    "insufficient_quota",
)


def _is_usage_limit_error(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(phrase in lower for phrase in _USAGE_LIMIT_PHRASES)


def _summarize_cli_error(stderr: str, stdout: str, max_len: int = 500) -> str:
    """Extract the most actionable line from verbose CLI output."""
    raw = (stderr or "").strip() or (stdout or "").strip()
    if not raw:
        return "Unknown error"

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return "Unknown error"

    signals = (
        "error:",
        "failed",
        "exception",
        "traceback",
        "denied",
        "unauthorized",
        "forbidden",
        "not found",
        "disconnected",
        "timed out",
    )
    for line in reversed(lines):
        lower = line.lower()
        if any(sig in lower for sig in signals):
            return line[:max_len]

    return lines[-1][:max_len]


def _is_codex_cli_auto_model(model: str | None) -> bool:
    return _is_provider_default_override(model)


# ---------------------------------------------------------------------------
# Shared retry constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 5
_TIMEOUT = 300
_RATE_LIMIT_BASE_WAIT = 10


def _retry_wait(attempt: int) -> float:
    return min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)


def _collapse_messages_for_single_prompt(messages: list[dict]) -> str:
    """Flatten chat messages into one prompt string for single-shot CLIs."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue
        if role == "system":
            parts.append(f"SYSTEM:\n{content}")
        elif role == "assistant":
            parts.append(f"PREVIOUS RESPONSE:\n{content}")
        else:
            parts.append(content)
    return "\n\n---\n\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Claude CLI Client
# ---------------------------------------------------------------------------

class ClaudeCLIClient:
    """LLM client via the Claude Code CLI subprocess (`claude -p`).

    No API key needed — uses the existing Claude Code session/subscription.
    """

    def __init__(self, model: str = "sonnet") -> None:
        self.model = model
        self.executable = shutil.which("claude") or "claude"

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
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

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        cmd = [self.executable, "-p", "--model", self.model]
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
                    if _is_usage_limit_error(error_msg):
                        raise UsageLimitError(
                            f"Claude usage limit: {error_msg[:300]}",
                            raw_message=error_msg,
                        )
                    if attempt < _MAX_RETRIES - 1:
                        wait = _retry_wait(attempt)
                        log.warning("Claude CLI exit %d: %s. Retry in %ds (%d/%d)",
                                    result.returncode, error_msg[:200], wait, attempt + 1, _MAX_RETRIES)
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Claude CLI failed (exit {result.returncode}): {error_msg[:500]}")

                output = result.stdout.strip()
                if not output:
                    if attempt < _MAX_RETRIES - 1:
                        log.warning("Claude CLI empty output, retrying...")
                        time.sleep(5)
                        continue
                    raise RuntimeError("Claude CLI returned empty output")

                return output

            except subprocess.TimeoutExpired:
                if attempt < _MAX_RETRIES - 1:
                    wait = _retry_wait(attempt)
                    log.warning("Claude CLI timeout, retry in %ds (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
                    time.sleep(wait)
                    continue
                raise

        raise RuntimeError("Claude CLI failed after all retries")

    def ask(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Gemini CLI Client
# ---------------------------------------------------------------------------

class GeminiCLIClient:
    """LLM client via Gemini CLI in headless mode with stdin-fed prompts."""

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model
        self.executable = shutil.which("gemini") or "gemini"

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        _ = temperature, max_tokens  # Gemini CLI controls these internally for now.
        prompt = _collapse_messages_for_single_prompt(messages)
        cmd = [
            self.executable,
            "-p",
            "",
            "--model",
            self.model,
            "--output-format",
            "text",
        ]

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
                )

                if result.returncode != 0:
                    error_msg = _summarize_cli_error(result.stderr, result.stdout)
                    if _is_usage_limit_error(error_msg):
                        raise UsageLimitError(
                            f"Gemini CLI usage limit: {error_msg[:300]}",
                            raw_message=error_msg,
                        )
                    if attempt < _MAX_RETRIES - 1:
                        wait = _retry_wait(attempt)
                        log.warning("Gemini CLI exit %d: %s. Retry in %ds (%d/%d)",
                                    result.returncode, error_msg[:200], wait, attempt + 1, _MAX_RETRIES)
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Gemini CLI failed (exit {result.returncode}): {error_msg[:500]}")

                output = result.stdout.strip()
                if not output:
                    if attempt < _MAX_RETRIES - 1:
                        log.warning("Gemini CLI empty output, retrying...")
                        time.sleep(5)
                        continue
                    raise RuntimeError("Gemini CLI returned empty output")

                return output

            except subprocess.TimeoutExpired:
                if attempt < _MAX_RETRIES - 1:
                    wait = _retry_wait(attempt)
                    log.warning("Gemini CLI timeout, retry in %ds (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
                    time.sleep(wait)
                    continue
                raise

        raise RuntimeError("Gemini CLI failed after all retries")

    def ask(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Gemini API Client
# ---------------------------------------------------------------------------

class GeminiClient:
    """LLM client for Google Gemini API.

    Requires: pip install google-generativeai
    Env var:  GEMINI_API_KEY
    """

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise RuntimeError(
                    "google-generativeai not installed. Run: pip install google-generativeai"
                )
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY not set in environment or ~/.applypilot/.env")
            genai.configure(api_key=api_key)
            self._client = genai
        return self._client

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        genai = self._get_client()

        # Separate system prompt
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        system_prompt = "\n\n".join(system_parts) if system_parts else None

        # Convert remaining messages to Gemini format
        # Gemini roles: "user" | "model" (not "assistant")
        history = []
        last_user = None
        for msg in messages:
            if msg["role"] == "system":
                continue
            role = "model" if msg["role"] == "assistant" else "user"
            history.append({"role": role, "parts": [msg["content"]]})

        # Last user message becomes the actual prompt
        # Gemini's start_chat takes history *before* the final turn
        if history and history[-1]["role"] == "user":
            last_user = history[-1]["parts"][0]
            history = history[:-1]
        else:
            last_user = ""

        import google.generativeai as genai_mod
        kwargs: dict = {"model_name": self.model}
        if system_prompt:
            kwargs["system_instruction"] = system_prompt

        model = genai_mod.GenerativeModel(**kwargs)

        gen_config = genai_mod.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        for attempt in range(_MAX_RETRIES):
            try:
                chat = model.start_chat(history=history)
                response = chat.send_message(last_user, generation_config=gen_config)
                return response.text.strip()

            except Exception as e:
                err_str = str(e)
                if _is_usage_limit_error(err_str):
                    raise UsageLimitError(f"Gemini usage limit: {err_str[:300]}", raw_message=err_str)
                if attempt < _MAX_RETRIES - 1:
                    wait = _retry_wait(attempt)
                    log.warning("Gemini error: %s. Retry in %ds (%d/%d)",
                                err_str[:200], wait, attempt + 1, _MAX_RETRIES)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Gemini failed after {_MAX_RETRIES} attempts: {err_str[:500]}")

        raise RuntimeError("Gemini failed after all retries")

    def ask(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Codex CLI Client
# ---------------------------------------------------------------------------

class CodexCLIClient:
    """LLM client via Codex CLI (`codex exec`)."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self.executable = shutil.which("codex") or "codex"
        self.exec_cwd = (os.environ.get("APPLYPILOT_CODEX_CWD") or tempfile.gettempdir()).strip()
        if not self.exec_cwd:
            self.exec_cwd = tempfile.gettempdir()
        try:
            os.makedirs(self.exec_cwd, exist_ok=True)
        except OSError:
            self.exec_cwd = tempfile.gettempdir()

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        _ = temperature, max_tokens  # Codex CLI controls these internally for now.
        prompt = _collapse_messages_for_single_prompt(messages)
        tmp = tempfile.NamedTemporaryFile(prefix="applypilot_codex_", suffix=".txt", delete=False)
        output_file = tmp.name
        tmp.close()
        cmd = [
            self.executable,
            "exec",
            "-C",
            self.exec_cwd,
            "--skip-git-repo-check",
            "--output-last-message",
            output_file,
        ]
        if not _is_codex_cli_auto_model(self.model):
            cmd[4:4] = ["--model", self.model]

        try:
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
                    )

                    if result.returncode != 0:
                        raw_error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                        error_msg = _summarize_cli_error(result.stderr, result.stdout)
                        if _is_usage_limit_error(raw_error):
                            raise UsageLimitError(
                                f"Codex CLI usage limit: {raw_error[:300]}",
                                raw_message=raw_error,
                            )
                        if attempt < _MAX_RETRIES - 1:
                            wait = _retry_wait(attempt)
                            log.warning("Codex CLI exit %d: %s. Retry in %ds (%d/%d)",
                                        result.returncode, error_msg[:200], wait, attempt + 1, _MAX_RETRIES)
                            time.sleep(wait)
                            continue
                        raise RuntimeError(f"Codex CLI failed (exit {result.returncode}): {error_msg}")

                    output = ""
                    if os.path.exists(output_file):
                        try:
                            with open(output_file, "r", encoding="utf-8", errors="replace") as fh:
                                output = fh.read().strip()
                        except OSError:
                            output = ""
                    if not output:
                        output = result.stdout.strip()

                    if not output:
                        if attempt < _MAX_RETRIES - 1:
                            log.warning("Codex CLI empty output, retrying...")
                            time.sleep(5)
                            continue
                        raise RuntimeError("Codex CLI returned empty output")

                    return output

                except subprocess.TimeoutExpired:
                    if attempt < _MAX_RETRIES - 1:
                        wait = _retry_wait(attempt)
                        log.warning("Codex CLI timeout, retry in %ds (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
                        time.sleep(wait)
                        continue
                    raise

            raise RuntimeError("Codex CLI failed after all retries")
        finally:
            try:
                os.remove(output_file)
            except OSError:
                pass

    def ask(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# OpenAI API Client
# ---------------------------------------------------------------------------

class OpenAIClient:
    """LLM client for OpenAI API (GPT-4o, o1, etc.).

    Requires: pip install openai
    Env var:  OPENAI_API_KEY
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError(
                    "openai not installed. Run: pip install openai"
                )
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not set in environment or ~/.applypilot/.env")
            self._client = OpenAI(api_key=api_key)
        return self._client

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        # OpenAI messages are already in the right format
        client = self._get_client()

        for attempt in range(_MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()

            except Exception as e:
                err_str = str(e)
                if _is_usage_limit_error(err_str):
                    raise UsageLimitError(f"OpenAI usage limit: {err_str[:300]}", raw_message=err_str)
                if attempt < _MAX_RETRIES - 1:
                    wait = _retry_wait(attempt)
                    log.warning("OpenAI error: %s. Retry in %ds (%d/%d)",
                                err_str[:200], wait, attempt + 1, _MAX_RETRIES)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"OpenAI failed after {_MAX_RETRIES} attempts: {err_str[:500]}")

        raise RuntimeError("OpenAI failed after all retries")

    def ask(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_client(tier: str = "general"):
    """Instantiate the right client for the current provider and tier."""
    prov = _provider()
    model = _model(tier)

    if prov == "claude":
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude Code CLI not found on PATH. Install from https://claude.ai/code"
            )
        return ClaudeCLIClient(model=model)
    elif prov == "gemini":
        if shutil.which("gemini"):
            return GeminiCLIClient(model=model)
        return GeminiClient(model=model)
    elif prov == "codex":
        if shutil.which("codex"):
            return CodexCLIClient(model=model)
        log.warning("Codex CLI not found; falling back to OpenAI API client.")
        fallback_model = _PROVIDER_DEFAULTS["openai"][tier] if _is_codex_cli_auto_model(model) else model
        return OpenAIClient(model=fallback_model)
    elif prov == "openai":
        return OpenAIClient(model=model)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{prov}'. Choose: claude, gemini, openai, codex"
        )


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_instance = None
_instance_key: tuple[str, str] | None = None
_tailor_instance = None
_tailor_instance_key: tuple[str, str] | None = None


def get_client():
    """Return the module-level LLM client singleton (general tier)."""
    global _instance, _instance_key
    prov = _provider()
    model = _model("general")
    key = (prov, model)
    if _instance is None or _instance_key != key:
        log.info("LLM provider: %s  model: %s", prov, model)
        _instance = _make_client("general")
        _instance_key = key
    return _instance


def get_tailor_client():
    """Return a dedicated high-quality client for the tailoring stage."""
    global _tailor_instance, _tailor_instance_key
    prov = _provider()
    model = _model("tailor")
    key = (prov, model)
    if _tailor_instance is None or _tailor_instance_key != key:
        log.info("Tailor LLM: %s  model: %s", prov, model)
        _tailor_instance = _make_client("tailor")
        _tailor_instance_key = key
    return _tailor_instance
