"""Independent, opt-in settings for native ReAct progress reminders."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

logger = logging.getLogger(__name__)
PREFIX = "QWENPAW_PROGRESS_REMINDER_"


@dataclass(frozen=True)
class ProgressReminderConfig:
    enabled: bool = False
    interval_seconds: int = 600

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Progress reminder enabled must be a boolean")
        value = self.interval_seconds
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(
                "Progress reminder interval_seconds must be a positive integer"
            )

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> ProgressReminderConfig:
        env = os.environ if environ is None else environ
        raw = env.get(PREFIX + "ENABLED", "0").strip().lower()
        if raw not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            logger.warning("Invalid %s; using default", PREFIX + "ENABLED")
        try:
            raw_interval = env.get(PREFIX + "INTERVAL_SECONDS", "600")
            interval = int(raw_interval)
            if isinstance(raw_interval, bool) or interval < 1:
                raise ValueError
        except (ValueError, TypeError):
            logger.warning(
                "Invalid %s; using 600", PREFIX + "INTERVAL_SECONDS"
            )
            interval = 600
        return cls(
            enabled=raw in {"1", "true", "yes", "on"},
            interval_seconds=interval,
        )
