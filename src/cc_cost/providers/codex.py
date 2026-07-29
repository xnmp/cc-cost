from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cc_cost.content import block, message_blocks, tail, unique
from cc_cost.domain import ContentBlock, PassTrace, Session, Step, TokenUsage, Turn
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


def _response_blocks(payload: dict[str, Any]) -> tuple[ContentBlock, ...]:
    payload_type = payload.get("type")
    if payload_type in {"message", "agent_message"}:
        default_role = "tool" if payload_type == "agent_message" else "unknown"
        return message_blocks(
            payload,
            default_role=str(payload.get("role") or default_role),
        )
    if payload_type in {"function_call", "custom_tool_call", "tool_search_call"}:
        value = payload.get("arguments")
        if value is None:
            value = payload.get("input")
        item = block(
            "assistant",
            "tool_call",
            value,
            label=str(
                payload.get("name")
                or ("tool search" if payload_type == "tool_search_call" else "tool")
            ),
            call_id=str(payload.get("call_id") or ""),
        )
        return (item,) if item else ()
    if payload_type in {
        "function_call_output",
        "custom_tool_call_output",
        "tool_search_output",
    }:
        value = payload.get("output")
        if value is None:
            value = payload.get("tools")
        item = block(
            "tool",
            "tool_result",
            value,
            label=str(payload.get("call_id") or "tool result"),
            call_id=str(payload.get("call_id") or ""),
        )
        return (item,) if item else ()
    if payload_type == "reasoning":
        summary = payload.get("summary")
        if not isinstance(summary, list):
            return ()
        texts = [
            item["text"]
            for item in summary
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        item = block("assistant", "reasoning", "\n\n".join(texts), label="reasoning")
        return (item,) if item else ()
    return ()


def _is_input(block: ContentBlock) -> bool:
    return block.role in {"user", "developer", "system", "tool"}


def parse_codex(path: Path) -> Session:
    meta: dict[str, Any] = {}
    turns: list[Turn] = []
    steps: list[Step] | None = None
    started_at: datetime | None = None
    current_model = ""
    previous_total = (0, 0, 0, 0)
    context: list[ContentBlock] = []
    pending: list[ContentBlock] = []
    response_observed = False

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
        if event_type == "response_item":
            pending.extend(item for item in _response_blocks(payload) if item not in pending)
            response_observed = True
            continue
        if event_type != "event_msg":
            continue
        payload_type = payload.get("type")
        if payload_type in {"agent_message", "user_message"}:
            role = "assistant" if payload_type == "agent_message" else "user"
            item = block(role, "message", payload.get("message"))
            if item and item not in pending:
                pending.append(item)
            continue
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
            last = _counts(info.get("last_token_usage"))
            usage = _usage_from_delta(last, (0, 0, 0, 0)) if last else None
            if usage is None:
                usage = _usage_from_delta(total, previous_total)
            previous_total = total
            if (
                steps is not None
                and usage is not None
                and usage.total
                and (pending or response_observed)
            ):
                input_blocks = unique(item for item in pending if _is_input(item))
                output_blocks = unique(item for item in pending if not _is_input(item))
                cached_preview, truncated = tail((*context, *input_blocks))
                steps.append(
                    Step(
                        model=current_model,
                        usage=usage,
                        trace=PassTrace(
                            input=input_blocks or cached_preview,
                            output=output_blocks,
                            cached_preview=cached_preview,
                            cached_preview_truncated=truncated,
                        ),
                    )
                )
                context.extend(unique(pending))
                pending.clear()
                response_observed = False
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
