"""Environment settings for optional, request-scoped failure recovery."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

logger = logging.getLogger(__name__)
PREFIX = "QWENPAW_FAILURE_LOOP_"


@dataclass(frozen=True)
class FailureLoopConfig:
    """Enable model review and bound its optional advice to ReAct."""

    enabled: bool = False
    check_interval: int = 5
    max_hint_tokens: int = 512

    def __post_init__(self) -> None:
        if (
            isinstance(self.check_interval, bool)
            or not isinstance(self.check_interval, int)
            or self.check_interval < 1
        ):
            raise ValueError(
                "Failure-loop check interval must be a positive number of rounds"
            )
        if (
            isinstance(self.max_hint_tokens, bool)
            or not isinstance(self.max_hint_tokens, int)
            or self.max_hint_tokens < 1
        ):
            raise ValueError(
                "Failure-loop hint budget must be a positive integer"
            )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "FailureLoopConfig":
        env = os.environ if environ is None else environ

        def boolean(key: str, default: bool) -> bool:
            raw = env.get(PREFIX + key)
            if raw is None:
                return default
            value = raw.strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off"}:
                return False
            logger.warning("Invalid %s; using default", PREFIX + key)
            return default

        def positive(key: str, default: int) -> int:
            try:
                value = int(env.get(PREFIX + key, str(default)))
                if value > 0:
                    return value
            except (ValueError, TypeError):
                pass
            logger.warning("Invalid %s; using %d", PREFIX + key, default)
            return default

        return cls(
            enabled=boolean("ENABLED", False),
            check_interval=positive("CHECK_INTERVAL", 5),
            max_hint_tokens=positive("MAX_HINT_TOKENS", 512),
        )
