"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import os
import re
import sys

from nanobot import __version__
from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.session.manager import (
    clear_session_reasoning_effort_override,
    describe_session_reasoning_effort,
    set_session_reasoning_effort_override,
)
from nanobot.utils.helpers import build_status_content

# Pattern to match $skill-name tokens (word chars + hyphens)
_SKILL_REF = re.compile(r"\$([A-Za-z][A-Za-z0-9_-]*)")
_THINKING_LEVELS = ("low", "medium", "high")
_THINKING_PICKER_ACTIONS = (*_THINKING_LEVELS, "off")


def _get_session_and_default_reasoning(ctx: CommandContext):
    """Resolve the current session and provider default reasoning effort."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    generation = getattr(loop.provider, "generation", None)
    default_effort = getattr(generation, "reasoning_effort", None)
    return session, default_effort


def _build_thinking_usage() -> str:
    """Build canonical usage text for the /thinking command."""
    choices = "|".join(["off", *_THINKING_LEVELS])
    return f"Use: /thinking {choices}"


def _build_thinking_status_message(level: str, source: str) -> str:
    """Build a human-readable status line for chat thinking level."""
    return f"Thinking level for this chat: {level}\nSource: {source}"


def _build_thinking_picker_text(level: str, source: str) -> str:
    """Build Telegram-friendly picker text for interactive thinking selection."""
    return f"{_build_thinking_status_message(level, source)}\nChoose a level below."


def _build_thinking_picker_metadata(level: str, source: str) -> dict[str, object]:
    """Build Telegram-specific picker metadata from shared thinking state."""
    return {
        "_telegram_inline_keyboard": {
            "type": "thinking_picker",
            "level": level,
            "source": source,
            "actions": list(_THINKING_PICKER_ACTIONS),
        }
    }


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    tasks = loop._active_tasks.pop(msg.session_key, [])
    cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    sub_cancelled = await loop.subagents.cancel_by_session(msg.session_key)
    total = cancelled + sub_cancelled
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process in-place via os.execv."""
    msg = ctx.msg

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="Restarting...")


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session, default_effort = _get_session_and_default_reasoning(ctx)
    ctx_est = 0
    try:
        ctx_est, _ = loop.memory_consolidator.estimate_session_prompt_tokens(session)
    except Exception:
        pass
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)
    thinking_level, thinking_source = describe_session_reasoning_effort(session, default_effort)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_status_content(
            version=__version__,
            model=loop.model,
            start_time=loop._start_time,
            last_usage=loop._last_usage,
            context_window_tokens=loop.context_window_tokens,
            session_msg_count=len(session.get_history(max_messages=0)),
            context_tokens_estimate=ctx_est,
            thinking_level=thinking_level,
            thinking_source=thinking_source,
        ),
        metadata={"render_as": "text"},
    )


def _format_mcp_status_content(statuses: list[dict]) -> str:
    """Format MCP server status lines for human-readable command output."""
    if not statuses:
        return "No MCP servers configured."

    icon_map = {
        "connected": "[ok]",
        "failed": "[fail]",
        "uninitialized": "[init]",
        "connecting": "[wait]",
    }

    lines = ["MCP servers:"]
    for item in statuses:
        name = str(item.get("name") or "(unknown)")
        state = str(item.get("state") or "unknown")
        icon = icon_map.get(state, "[?]")
        transport = str(item.get("transport") or "unknown")
        registered = item.get("registered_tools") or []
        available = item.get("available_tools") or []
        lines.append(
            f"  {icon} {name} - {state} ({transport}) - tools: {len(registered)}/{len(available)}"
        )
        error = item.get("error")
        if error and state != "connected":
            lines.append(f"    error: {error}")

    return "\n".join(lines)


async def cmd_mcp(ctx: CommandContext) -> OutboundMessage:
    """Run a live MCP health check and summarize status for all configured servers."""
    check = getattr(ctx.loop, "refresh_mcp_status", None)
    statuses: list[dict] = []
    if callable(check):
        statuses = await check(reconnect=True)
    content = _format_mcp_status_content(statuses)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={"render_as": "text"},
    )


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Start a fresh session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    snapshot = session.messages[session.last_consolidated :]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(
            loop.memory_consolidator.remember_messages(snapshot),
            label="session snapshot memory",
        )
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="New session started.",
    )


async def cmd_thinking(ctx: CommandContext) -> OutboundMessage:
    """Inspect or change the chat-scoped thinking level."""
    loop = ctx.loop
    session, default_effort = _get_session_and_default_reasoning(ctx)
    arg = ctx.args.strip().lower()

    if not arg:
        level, source = describe_session_reasoning_effort(session, default_effort)
        metadata = {"render_as": "text"}
        content = f"{_build_thinking_status_message(level, source)}\n{_build_thinking_usage()}"
        if ctx.msg.channel == "telegram":
            metadata.update(_build_thinking_picker_metadata(level, source))
            content = _build_thinking_picker_text(level, source)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata=metadata,
        )

    if arg == "off":
        clear_session_reasoning_effort_override(session)
        loop.sessions.save(session)
        level, source = describe_session_reasoning_effort(session, default_effort)
        metadata: dict[str, object] = {"render_as": "text"}
        content = (
            "Thinking override cleared for this chat.\n"
            f"{_build_thinking_status_message(level, source)}"
        )
        if edit_message_id := ctx.msg.metadata.get("_telegram_thinking_edit_message_id"):
            metadata["_telegram_edit_message_id"] = edit_message_id
            metadata.update(_build_thinking_picker_metadata(level, source))
            content = _build_thinking_picker_text(level, source)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata=metadata,
        )

    try:
        level = set_session_reasoning_effort_override(session, arg)
    except ValueError:
        valid = ", ".join(["off", *_THINKING_LEVELS])
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                f"Invalid thinking level: {ctx.args.strip() or arg}\n"
                f"Supported values: {valid}\n{_build_thinking_usage()}"
            ),
            metadata={"render_as": "text"},
        )

    loop.sessions.save(session)
    metadata: dict[str, object] = {"render_as": "text"}
    content = f"Thinking level set for this chat.\n{_build_thinking_status_message(level, 'chat override')}"
    if edit_message_id := ctx.msg.metadata.get("_telegram_thinking_edit_message_id"):
        metadata["_telegram_edit_message_id"] = edit_message_id
        metadata.update(_build_thinking_picker_metadata(level, "chat override"))
        content = _build_thinking_picker_text(level, "chat override")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata=metadata,
    )


async def cmd_skill_list(ctx: CommandContext) -> OutboundMessage:
    """List all available skills."""
    loader = ctx.loop.context.skills
    skills = loader.list_skills(filter_unavailable=False)
    if not skills:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="No skills found.",
        )
    lines = ["Available skills (use $<name> to activate):"]
    for s in skills:
        desc = loader._get_skill_description(s["name"])
        available = loader._check_requirements(loader._get_skill_meta(s["name"]))
        mark = "✓" if available else "✗"
        lines.append(f"  {mark} {s['name']} — {desc}")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata={"render_as": "text"},
    )


async def intercept_skill_refs(ctx: CommandContext) -> OutboundMessage | None:
    """Scan message for $skill-name references and inject matching skills."""
    refs = _SKILL_REF.findall(ctx.msg.content)
    if not refs:
        return None
    loader = ctx.loop.context.skills
    skill_names = {s["name"] for s in loader.list_skills(filter_unavailable=True)}
    matched = []
    for name in dict.fromkeys(refs):  # deduplicate, preserve order
        if name in skill_names:
            matched.append(name)
    if not matched:
        return None
    # Strip matched $refs from the message
    message = ctx.msg.content
    for name in matched:
        message = re.sub(rf"\${re.escape(name)}\b", "", message)
    message = message.strip()
    # Build injected content
    skill_blocks = []
    for name in matched:
        content = loader.load_skill(name)
        if content:
            stripped = loader._strip_frontmatter(content)
            skill_blocks.append(f'<skill-content name="{name}">\n{stripped}\n</skill-content>')
    if not skill_blocks:
        return None
    names = ", ".join(f"'{n}'" for n in matched)
    injected = (
        f"<system-reminder>\n"
        f"The user activated skill(s) {names} via $-reference. "
        f"The following skill content was auto-appended by the system.\n"
        + "\n".join(skill_blocks)
        + "\n</system-reminder>"
    )
    ctx.msg.content = f"{injected}\n\n{message}" if message else injected
    return None  # fall through to LLM


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(),
        metadata={"render_as": "text"},
    )


def build_help_text() -> str:
    """Build canonical help text shared across channels."""
    lines = [
        "🐈 nanobot commands:",
        "/new — Start a new conversation",
        "/stop — Stop the current task",
        "/restart — Restart the bot",
        "/status — Show bot status",
        "/thinking — Show or change chat thinking level",
        "/mcp — Check MCP server status",
        "/skills — List available skills",
        "$<name> — Activate a skill inline (e.g. $weather what's the forecast)",
        "/help — Show available commands",
    ]
    return "\n".join(lines)


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    router.priority("/stop", cmd_stop)
    router.priority("/restart", cmd_restart)
    router.priority("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/status", cmd_status)
    router.exact("/thinking", cmd_thinking)
    router.prefix("/thinking ", cmd_thinking)
    router.exact("/mcp", cmd_mcp)
    router.exact("/help", cmd_help)
    router.exact("/skills", cmd_skill_list)
    router.intercept(intercept_skill_refs)
