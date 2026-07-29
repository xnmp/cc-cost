from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cc_cost.domain import Session, Step, TokenUsage, Turn
from cc_cost.jsonl import read_jsonl


def _real_user(event: dict[str, Any]) -> bool:
    if event.get("type") != "user":
        return False
    content = event.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") != "tool_result" for block in content
    )


def _usage(raw: dict[str, Any]) -> TokenUsage:
    creation = raw.get("cache_creation") or {}
    cache_write_5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
    cache_write_1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    if not creation:
        cache_write_5m = int(raw.get("cache_creation_input_tokens") or 0)
    return TokenUsage(
        input=int(raw.get("input_tokens") or 0),
        cache_read=int(raw.get("cache_read_input_tokens") or 0),
        cache_write_5m=cache_write_5m,
        cache_write_1h=cache_write_1h,
        output=int(raw.get("output_tokens") or 0),
    )


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _spawn_ids(message: dict[str, Any]) -> set[str]:
    content = message.get("content")
    if not isinstance(content, list):
        return set()
    return {
        str(block["id"])
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id")
    }


@dataclass(slots=True)
class _StepRecord:
    model: str
    usage: TokenUsage
    spawn_ids: set[str] = field(default_factory=set)
    subagent: bool = False


def _assistant_steps(
    entries: tuple[dict[str, Any], ...], *, include_sidechains: bool
) -> tuple[Step, ...]:
    grouped: dict[str, _StepRecord] = {}
    order: list[str] = []
    for offset, event in enumerate(entries):
        if event.get("type") != "assistant" or event.get("isApiErrorMessage") is True:
            continue
        is_sidechain = bool(event.get("isSidechain"))
        if is_sidechain and not include_sidechains:
            continue
        message = event.get("message", {})
        model = str(message.get("model") or "")
        if model == "<synthetic>":
            continue
        message_id = str(message.get("id") or event.get("requestId") or f"line:{offset}")
        record = grouped.get(message_id)
        if record is None:
            record = _StepRecord(
                model=model,
                usage=_usage(message.get("usage") or {}),
                subagent=is_sidechain,
            )
            grouped[message_id] = record
            order.append(message_id)
        record.spawn_ids.update(_spawn_ids(message))
    return tuple(
        Step(
            model=grouped[message_id].model,
            usage=grouped[message_id].usage,
            spawn_ids=tuple(sorted(grouped[message_id].spawn_ids)),
            subagent=grouped[message_id].subagent,
        )
        for message_id in order
        if grouped[message_id].usage.total
    )


def parse_claude(path: Path) -> Session:
    entries = tuple(read_jsonl(path))
    boundaries = [
        index
        for index, event in enumerate(entries)
        if not event.get("isSidechain") and _real_user(event)
    ]
    boundaries.append(len(entries))
    turns: list[Turn] = []

    for number, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False), 1):
        steps = _assistant_steps(entries[start + 1 : end], include_sidechains=True)
        turns.append(
            Turn(
                number=number,
                steps=steps,
                started_at=_parse_time(entries[start].get("timestamp")),
            )
        )

    first = entries[0] if entries else {}
    return Session(
        id=str(first.get("sessionId") or path.stem),
        provider="claude",
        path=path,
        cwd=None,
        started_at=_parse_time(first.get("timestamp")),
        turns=tuple(turns),
    )


def parse_claude_agent(path: Path, *, tool_use_id: str, label: str) -> Session:
    entries = tuple(read_jsonl(path))
    steps = _assistant_steps(entries, include_sidechains=True)
    first = entries[0] if entries else {}
    return Session(
        id=tool_use_id,
        provider="claude",
        path=path,
        cwd=None,
        started_at=_parse_time(first.get("timestamp")),
        turns=(Turn(number=1, steps=steps),),
        label=label,
    )
