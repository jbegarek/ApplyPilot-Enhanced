"""Unified LLM client for ApplyPilot using LiteLLM-compatible configuration.

This module is mid-migration from the earlier provider-specific client layer to
LiteLLM-style model resolution. To keep the rest of the codebase stable during
that migration, it preserves the existing `UsageLimitError`, `_model()`,
`_make_client()`, `get_client()`, and `get_tailor_client()` surface while
introducing `LLMConfig`, `LLMClient`, and `resolve_llm_config()`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import os
from typing import Any, Literal, TypedDict

try:
    import litellm  # type: ignore
except ImportError:  # pragma: no cover - exercised only when dependency missing.
    class _LiteLLMStub:
        suppress_debug_info = False

        @staticmethod
        def completion(**_: object) -> object:
            raise RuntimeError(
                "litellm is not installed. Add it to the environment to use the migrated LLM stack."
            )

    litellm = _LiteLLMStub()

log = logging.getLogger(__name__)

_MAX_RETRIES = 5
_TIMEOUT = 120
_DEFAULT_LOCAL_MODEL = "openai/local-model"
_PROVIDER_ALIASES = {
    "claude": "anthropic",
    "gemini": "gemini",
    "openai": "openai",
    "codex": "openai",
    "anthropic": "anthropic",
}
_DEFAULT_MODEL_BY_PROVIDER = {
    "anthropic": {"general": "anthropic/claude-haiku-4-5", "tailor": "anthropic/claude-sonnet-4-5"},
    "gemini": {"general": "gemini/gemini-3.0-flash", "tailor": "gemini-2.5-pro"},
    "openai": {"general": "openai/gpt-4o-mini", "tailor": "openai/gpt-4o"},
}
_INFERRED_SOURCE_ORDER: tuple[tuple[str, str], ...] = (
    ("gemini", "GEMINI_API_KEY"),
    ("openai", "OPENAI_API_KEY"),
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("openai", "LLM_URL"),
)
_PROVIDER_API_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class UsageLimitError(Exception):
    """Raised when an LLM provider reports a quota or rate-limit condition."""

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


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_base: str | None
    model: str
    api_key: str
    use_streaming: bool = False


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


def _env_get(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "")
    return "" if value is None else str(value).strip()


def _provider_from_model(model: str) -> str:
    provider, _, model_name = model.partition("/")
    if not provider or not model_name:
        raise RuntimeError(
            "LLM_MODEL must include a provider prefix (for example 'openai/gpt-4o-mini')."
        )
    return provider


def _infer_provider_and_source(env: Mapping[str, str]) -> tuple[str, str] | None:
    for provider, env_key in _INFERRED_SOURCE_ORDER:
        if _env_get(env, env_key):
            return provider, env_key
    return None


def _legacy_provider(env: Mapping[str, str]) -> str | None:
    provider = _env_get(env, "LLM_PROVIDER").lower()
    if not provider:
        return None
    return _PROVIDER_ALIASES.get(provider, provider)


def _provider_for_resolution(env: Mapping[str, str], tier: str = "general") -> str:
    explicit_provider = _legacy_provider(env)
    if explicit_provider:
        return explicit_provider

    model = _env_get(env, f"LLM_MODEL_{tier.upper()}") or _env_get(env, "LLM_MODEL")
    if model and "/" in model:
        return _provider_from_model(model)

    inferred = _infer_provider_and_source(env)
    if inferred:
        provider, _ = inferred
        return provider

    return "anthropic"


def _default_model(provider: str, tier: str = "general") -> str:
    if provider not in _DEFAULT_MODEL_BY_PROVIDER:
        return _DEFAULT_LOCAL_MODEL
    return _DEFAULT_MODEL_BY_PROVIDER[provider][tier]


def _resolve_model_for_provider(env: Mapping[str, str], provider: str, tier: str) -> str:
    tier_override = _env_get(env, f"LLM_MODEL_{tier.upper()}")
    if tier_override:
        if "/" in tier_override:
            return tier_override
        return f"{provider}/{tier_override}"

    model = _env_get(env, "LLM_MODEL")
    if model:
        if "/" in model:
            return model
        return f"{provider}/{model}"

    return _default_model(provider, tier)


def resolve_llm_config(env: Mapping[str, str] | None = None, *, tier: str = "general") -> LLMConfig:
    """Resolve provider, model, API base, and auth material from environment."""
    env_map = env if env is not None else os.environ
    local_url = _env_get(env_map, "LLM_URL")
    explicit_provider = _legacy_provider(env_map)
    tier_model = _env_get(env_map, f"LLM_MODEL_{tier.upper()}")
    model = tier_model or _env_get(env_map, "LLM_MODEL")

    if model:
        if "/" in model:
            provider = _provider_from_model(model)
        elif explicit_provider:
            provider = explicit_provider
            model = f"{provider}/{model}"
        else:
            inferred = _infer_provider_and_source(env_map)
            if inferred:
                provider, _ = inferred
                model = f"{provider}/{model}"
            else:
                raise RuntimeError(
                    "LLM_MODEL must include a provider prefix (for example 'openai/gpt-4o-mini')."
                )
    elif explicit_provider:
        provider = explicit_provider
        model = _resolve_model_for_provider(env_map, provider, tier)
    else:
        inferred = _infer_provider_and_source(env_map)
        if not inferred:
            raise RuntimeError(
                "No LLM provider configured. Set one of GEMINI_API_KEY, OPENAI_API_KEY, "
                "ANTHROPIC_API_KEY, LLM_URL, or LLM_MODEL."
            )
        provider, source = inferred
        model = _DEFAULT_LOCAL_MODEL if source == "LLM_URL" else _default_model(provider, tier)

    api_key_env = _PROVIDER_API_KEY_ENV.get(provider, "LLM_API_KEY")
    api_key = _env_get(env_map, api_key_env) or _env_get(env_map, "LLM_API_KEY")
    if not api_key and not local_url:
        key_help = f"{api_key_env} or LLM_API_KEY" if provider in _PROVIDER_API_KEY_ENV else "LLM_API_KEY"
        raise RuntimeError(
            f"Missing credentials for LLM_MODEL '{model}'. Set {key_help}, or set LLM_URL for "
            "a local OpenAI-compatible endpoint."
        )

    use_streaming = _env_get(env_map, "LLM_STREAMING_MODE").lower() in {"1", "true", "yes"}
    return LLMConfig(
        provider=provider,
        api_base=local_url.rstrip("/") if local_url else None,
        model=model,
        api_key=api_key,
        use_streaming=use_streaming,
    )


class LLMClient:
    """Thin wrapper over LiteLLM completion()."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self._use_streaming = config.use_streaming
        litellm.suppress_debug_info = True

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        max_output_tokens: int = 10000,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: int = _TIMEOUT,
        num_retries: int = _MAX_RETRIES,
        drop_params: bool = True,
        **extra: Any,
    ) -> str:
        if max_tokens is not None:
            max_output_tokens = max_tokens

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "timeout": timeout,
            "num_retries": num_retries,
            "drop_params": drop_params,
            "api_key": self.config.api_key or None,
            "api_base": self.config.api_base or None,
            **extra,
        }
        if temperature is not None:
            request_kwargs["temperature"] = temperature

        try:
            response = litellm.completion(**request_kwargs)
            choices = getattr(response, "choices", None)
            if not choices:
                raise RuntimeError("LLM response contained no choices.")
            content = response.choices[0].message.content
            text = content.strip() if isinstance(content, str) else str(content).strip()
            if not text:
                raise RuntimeError("LLM response contained no text content.")
            return text
        except Exception as exc:
            err_str = str(exc)
            if _is_usage_limit_error(err_str):
                raise UsageLimitError(f"LLM usage limit: {err_str[:300]}", raw_message=err_str) from exc
            raise RuntimeError(f"LLM request failed ({self.provider}/{self.model}): {exc}") from exc

    def ask(self, prompt: str, **kwargs: Any) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        return None


def _provider() -> str:
    return _provider_for_resolution(os.environ, tier="general")


def _model(tier: str = "general") -> str:
    env = os.environ
    provider = _provider_for_resolution(env, tier=tier)
    return _resolve_model_for_provider(env, provider, tier)


def _make_client(tier: str = "general") -> LLMClient:
    return LLMClient(resolve_llm_config(tier=tier))


_instance: LLMClient | None = None
_instance_key: tuple[str, str] | None = None
_tailor_instance: LLMClient | None = None
_tailor_instance_key: tuple[str, str] | None = None


def get_client() -> LLMClient:
    global _instance, _instance_key
    config = resolve_llm_config(tier="general")
    key = (config.provider, config.model)
    if _instance is None or _instance_key != key:
        log.info("LLM provider: %s  model: %s", config.provider, config.model)
        _instance = LLMClient(config)
        _instance_key = key
    return _instance


def get_tailor_client() -> LLMClient:
    global _tailor_instance, _tailor_instance_key
    config = resolve_llm_config(tier="tailor")
    key = (config.provider, config.model)
    if _tailor_instance is None or _tailor_instance_key != key:
        log.info("Tailor LLM: %s  model: %s", config.provider, config.model)
        _tailor_instance = LLMClient(config)
        _tailor_instance_key = key
    return _tailor_instance
