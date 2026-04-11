import asyncio
import json

import pytest

from nanobot.cron.service import CronService, apply_cron_history_profile
from nanobot.cron.types import CronSchedule, cron_history_profile_max_messages
from nanobot.session.manager import Session


def _tool_turn(prefix: str, idx: int) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"{prefix}_{idx}_a",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                },
                {
                    "id": f"{prefix}_{idx}_b",
                    "type": "function",
                    "function": {"name": "y", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": f"{prefix}_{idx}_a", "name": "x", "content": "ok"},
        {"role": "tool", "tool_call_id": f"{prefix}_{idx}_b", "name": "y", "content": "ok"},
    ]


def _assert_no_orphans(history: list[dict]) -> None:
    declared = {
        tc["id"]
        for message in history
        if message.get("role") == "assistant"
        for tc in (message.get("tool_calls") or [])
    }
    orphan_ids = [
        message.get("tool_call_id")
        for message in history
        if message.get("role") == "tool" and message.get("tool_call_id") not in declared
    ]
    assert orphan_ids == []


def test_add_job_rejects_unknown_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    with pytest.raises(ValueError, match="unknown timezone 'America/Vancovuer'"):
        service.add_job(
            name="tz typo",
            schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancovuer"),
            message="hello",
        )

    assert service.list_jobs(include_disabled=True) == []


def test_add_job_accepts_valid_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = service.add_job(
        name="tz ok",
        schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancouver"),
        message="hello",
    )

    assert job.schedule.tz == "America/Vancouver"
    assert job.state.next_run_at_ms is not None
    assert job.profile == "compact"


def test_add_job_persists_default_compact_profile(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.add_job(
        name="profile default",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )

    assert job.profile == "compact"

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["jobs"][0]["profile"] == "compact"


def test_load_store_treats_missing_profile_as_legacy_normal(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.add_job(
        name="legacy profile",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    raw["jobs"][0].pop("profile", None)
    store_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    fresh = CronService(store_path)
    loaded = fresh.get_job(job.id)

    assert loaded is not None
    assert loaded.profile == "normal"


def test_apply_cron_history_profile_stateless_clears_session() -> None:
    session = Session(key="cron:test")
    for idx in range(5):
        session.messages.append({"role": "user", "content": f"msg{idx}"})
    session.last_consolidated = 2

    apply_cron_history_profile(session, "stateless")

    assert session.messages == []
    assert session.last_consolidated == 0


def test_apply_cron_history_profile_compact_keeps_recent_suffix() -> None:
    session = Session(key="cron:test")
    max_messages = cron_history_profile_max_messages("compact")
    for idx in range(max_messages + 6):
        session.messages.append({"role": "user", "content": f"msg{idx}"})

    apply_cron_history_profile(session, "compact")

    assert len(session.messages) == max_messages
    assert session.messages[0]["content"] == f"msg{6}"
    assert session.messages[-1]["content"] == f"msg{max_messages + 5}"


def test_apply_cron_history_profile_normal_keeps_larger_suffix() -> None:
    session = Session(key="cron:test")
    max_messages = cron_history_profile_max_messages("normal")
    for idx in range(max_messages + 10):
        session.messages.append({"role": "user", "content": f"msg{idx}"})

    apply_cron_history_profile(session, "normal")

    assert len(session.messages) == max_messages
    assert session.messages[0]["content"] == "msg10"
    assert session.messages[-1]["content"] == f"msg{max_messages + 9}"


def test_apply_cron_history_profile_preserves_legal_tool_boundary() -> None:
    session = Session(key="cron:test")
    session.messages.append({"role": "user", "content": "old1"})
    session.messages.extend(_tool_turn("old1", 0))
    session.messages.append({"role": "user", "content": "old2"})
    session.messages.extend(_tool_turn("old2", 0))
    session.messages.append({"role": "user", "content": "keep"})
    session.messages.extend(_tool_turn("keep", 0))
    session.messages.append({"role": "assistant", "content": "done"})

    apply_cron_history_profile(session, "compact")

    history = session.get_history(max_messages=500)
    _assert_no_orphans(history)
    assert history[0]["role"] == "user"
    assert history[0]["content"] != "old1"


@pytest.mark.asyncio
async def test_execute_job_records_run_history(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path, on_job=lambda _: asyncio.sleep(0))
    job = service.add_job(
        name="hist",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )
    await service.run_job(job.id)

    loaded = service.get_job(job.id)
    assert loaded is not None
    assert len(loaded.state.run_history) == 1
    rec = loaded.state.run_history[0]
    assert rec.status == "ok"
    assert rec.duration_ms >= 0
    assert rec.error is None


@pytest.mark.asyncio
async def test_run_history_records_errors(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"

    async def fail(_):
        raise RuntimeError("boom")

    service = CronService(store_path, on_job=fail)
    job = service.add_job(
        name="fail",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )
    await service.run_job(job.id)

    loaded = service.get_job(job.id)
    assert len(loaded.state.run_history) == 1
    assert loaded.state.run_history[0].status == "error"
    assert loaded.state.run_history[0].error == "boom"


@pytest.mark.asyncio
async def test_run_history_trimmed_to_max(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path, on_job=lambda _: asyncio.sleep(0))
    job = service.add_job(
        name="trim",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )
    for _ in range(25):
        await service.run_job(job.id)

    loaded = service.get_job(job.id)
    assert len(loaded.state.run_history) == CronService._MAX_RUN_HISTORY


@pytest.mark.asyncio
async def test_run_history_persisted_to_disk(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path, on_job=lambda _: asyncio.sleep(0))
    job = service.add_job(
        name="persist",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )
    await service.run_job(job.id)

    raw = json.loads(store_path.read_text())
    history = raw["jobs"][0]["state"]["runHistory"]
    assert len(history) == 1
    assert history[0]["status"] == "ok"
    assert "runAtMs" in history[0]
    assert "durationMs" in history[0]

    fresh = CronService(store_path)
    loaded = fresh.get_job(job.id)
    assert len(loaded.state.run_history) == 1
    assert loaded.state.run_history[0].status == "ok"


@pytest.mark.asyncio
async def test_running_service_honors_external_disable(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    called: list[str] = []

    async def on_job(job) -> None:
        called.append(job.id)

    service = CronService(store_path, on_job=on_job)
    job = service.add_job(
        name="external-disable",
        schedule=CronSchedule(kind="every", every_ms=200),
        message="hello",
    )
    await service.start()
    try:
        # Wait slightly to ensure file mtime is definitively different
        await asyncio.sleep(0.05)
        external = CronService(store_path)
        updated = external.enable_job(job.id, enabled=False)
        assert updated is not None
        assert updated.enabled is False

        await asyncio.sleep(0.35)
        assert called == []
    finally:
        service.stop()
