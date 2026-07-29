from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cc_cost.domain import Session, Step, TokenUsage, Turn
from cc_cost.jsonl import read_jsonl


def _datetime(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def _counts(raw: object) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, dict):
        return None
    return (
        int(raw.get("input_tokens") or 0),
        int(raw.get("cached_input_tokens") or 0),
        int(raw.get("cache_write_input_tokens") or 0),
        int(raw.get("output_tokens") or 0),
    )


def _usage_from_delta(
    current: tuple[int, int, int, int],
    previous: tuple[int, int, int, int],
) -> TokenUsage | None:
    delta = tuple(now - before for now, before in zip(current, previous, strict=True))
    if any(value < 0 for value in delta):
        return None
    total_input, cached, cache_write, output = delta
    return TokenUsage(
        input=max(0, total_input - cached - cache_write),
        cache_read=cached,
        cache_write_5m=cache_write,
        output=output,
    )


def _parent_id(source: object) -> str | None:
    if not isinstance(source, dict):
        return None
    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return None
    spawn = subagent.get("thread_spawn")
    return str(spawn["parent_thread_id"]) if isinstance(spawn, dict) and spawn.get(
        "parent_thread_id"
    ) else None


def _agent_label(source: object) -> str:
    if not isinstance(source, dict):
        return ""
    subagent = source.get("subagent")
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    if not isinstance(spawn, dict):
        return ""
    return str(spawn.get("agent_path") or spawn.get("agent_nickname") or "")


def parse_codex(path: Path) -> Session:
    meta: dict[str, Any] = {}
    turns: list[Turn] = []
    steps: list[Step] | None = None
    started_at: datetime | None = None
    current_model = ""
    previous_total = (0, 0, 0, 0)

    for event in read_jsonl(path):
        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if event_type == "session_meta":
            meta = payload
            continue
        if event_type == "turn_context":
            current_model = str(payload.get("model") or current_model)
            continue
        if event_type != "event_msg":
            continue
        payload_type = payload.get("type")
        if payload_type == "task_started":
            if steps is not None:
                turns.append(
                    Turn(
                        number=len(turns) + 1,
                        steps=tuple(steps),
                        started_at=started_at,
                        interrupted=True,
                    )
                )
            steps = []
            started_at = _datetime(payload.get("started_at"))
            continue
        if payload_type == "token_count":
            info = payload.get("info")
            if not isinstance(info, dict):
                continue
            total = _counts(info.get("total_token_usage"))
            if total is None or total == previous_total:
                continue
            usage = _usage_from_delta(total, previous_total)
            if usage is None:
                last = _counts(info.get("last_token_usage"))
                usage = _usage_from_delta(last, (0, 0, 0, 0)) if last else None
            previous_total = total
            if steps is not None and usage is not None and usage.total:
                steps.append(Step(model=current_model, usage=usage))
            continue
        if payload_type in {"task_complete", "turn_aborted"} and steps is not None:
            turns.append(
                Turn(
                    number=len(turns) + 1,
                    steps=tuple(steps),
                    started_at=started_at,
                    completed_at=_datetime(payload.get("completed_at")),
                    interrupted=payload_type == "turn_aborted",
                )
            )
            steps = None
            started_at = None

    if steps is not None:
        turns.append(
            Turn(
                number=len(turns) + 1,
                steps=tuple(steps),
                started_at=started_at,
                interrupted=False,
            )
        )

    source = meta.get("source")
    cwd = meta.get("cwd")
    return Session(
        id=str(meta.get("id") or meta.get("session_id") or path.stem),
        provider="codex",
        path=path,
        cwd=Path(cwd) if isinstance(cwd, str) else None,
        started_at=_datetime(meta.get("timestamp")),
        turns=tuple(turns),
        parent_id=_parent_id(source),
        label=_agent_label(source),
    )
