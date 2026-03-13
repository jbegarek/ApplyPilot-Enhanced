from __future__ import annotations

import logging

import applypilot.cli as cli


def test_configure_logging_quiets_noisy_sdk_loggers() -> None:
    cli._configure_logging(level="INFO")

    for name in ("litellm", "httpx", "openai"):
        logger = logging.getLogger(name)
        assert logger.level == logging.WARNING
        assert logger.propagate is True


def test_configure_logging_enables_verbose_sdk_loggers_in_debug() -> None:
    cli._configure_logging(level="DEBUG")

    for name in ("litellm", "httpx", "openai"):
        logger = logging.getLogger(name)
        assert logger.level == logging.INFO
        assert logger.propagate is True
