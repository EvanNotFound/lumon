"""Cron types."""

from dataclasses import dataclass, field
from typing import Literal

CronHistoryProfile = Literal["stateless", "compact", "normal"]
CRON_HISTORY_PROFILES: tuple[CronHistoryProfile, ...] = ("stateless", "compact", "normal")
DEFAULT_CRON_HISTORY_PROFILE: CronHistoryProfile = "compact"
LEGACY_CRON_HISTORY_PROFILE: CronHistoryProfile = "normal"
CRON_HISTORY_PROFILE_MAX_MESSAGES: dict[CronHistoryProfile, int] = {
    "stateless": 0,
    "compact": 8,
    "normal": 24,
}


def normalize_cron_history_profile(
    value: str | None,
    *,
    fallback: CronHistoryProfile,
) -> CronHistoryProfile:
    """Normalize a persisted or user-provided cron history profile."""
    normalized = (value or "").strip().lower()
    if normalized in CRON_HISTORY_PROFILES:
        return CRON_HISTORY_PROFILES[CRON_HISTORY_PROFILES.index(normalized)]
    return fallback


def cron_history_profile_max_messages(profile: CronHistoryProfile) -> int:
    """Return the retained message budget for one cron history profile."""
    return CRON_HISTORY_PROFILE_MAX_MESSAGES[profile]


@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""

    kind: Literal["at", "every", "cron"]
    # For "at": timestamp in ms
    at_ms: int | None = None
    # For "every": interval in ms
    every_ms: int | None = None
    # For "cron": cron expression (e.g. "0 9 * * *")
    expr: str | None = None
    # Timezone for cron expressions
    tz: str | None = None


@dataclass
class CronPayload:
    """What to do when the job runs."""

    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    # Deliver response to channel
    deliver: bool = False
    channel: str | None = None  # e.g. "whatsapp"
    to: str | None = None  # e.g. phone number


@dataclass
class CronRunRecord:
    """A single execution record for a cron job."""

    run_at_ms: int
    status: Literal["ok", "error", "skipped"]
    duration_ms: int = 0
    error: str | None = None


@dataclass
class CronJobState:
    """Runtime state of a job."""

    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    run_history: list[CronRunRecord] = field(default_factory=list)


@dataclass
class CronJob:
    """A scheduled job."""

    id: str
    name: str
    enabled: bool = True
    profile: CronHistoryProfile = DEFAULT_CRON_HISTORY_PROFILE
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0
    updated_at_ms: int = 0
    delete_after_run: bool = False


@dataclass
class CronStore:
    """Persistent store for cron jobs."""

    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
