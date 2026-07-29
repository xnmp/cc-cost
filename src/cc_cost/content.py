from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from cc_cost.domain import ContentBlock, ContentKind

CACHE_PREVIEW_CHARS = 8_000
INJECTED_CONTEXT_PREFIXES = (
    "<local-command",
    "<command-",
    "<recommended_plugins>",
    "# AGENTS.md instructions",
    "<environment_context>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<apps_instructions>",
    "<plugins_instructions>",
    "<skills_instructions>",
)


def pretty(value: object) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    return json.dumps(value, indent=2, ensure_ascii=False)


def block(
    role: str,
    kind: ContentKind,
    value: object,
    *,
    label: str = "",
    call_id: str = "",
) -> ContentBlock | None:
    if value is None:
        return None
    text = pretty(value) if kind in {"tool_call", "tool_result"} else str(value)
    return (
        ContentBlock(role=role, kind=kind, text=text, label=label, call_id=call_id)
        if text
        else None
    )


def unique(blocks: Iterable[ContentBlock]) -> tuple[ContentBlock, ...]:
    result: list[ContentBlock] = []
    seen: set[ContentBlock] = set()
    for item in blocks:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def is_prompt_context(block: ContentBlock) -> bool:
    if block.role in {"developer", "system"} or block.kind == "system":
        return True
    return block.role == "user" and block.text.lstrip().startswith(
        INJECTED_CONTEXT_PREFIXES
    )


def tail(
    blocks: Iterable[ContentBlock],
    limit: int = CACHE_PREVIEW_CHARS,
) -> tuple[tuple[ContentBlock, ...], bool]:
    values = tuple(blocks)
    remaining = limit
    selected: list[ContentBlock] = []
    truncated = False
    for item in reversed(values):
        if remaining <= 0:
            truncated = True
            break
        if len(item.text) <= remaining:
            selected.append(item)
            remaining -= len(item.text)
            continue
        selected.append(
            ContentBlock(
                role=item.role,
                kind=item.kind,
                text="… " + item.text[-remaining:],
                label=item.label,
                call_id=item.call_id,
            )
        )
        remaining = 0
        truncated = True
    if len(selected) < len(values):
        truncated = True
    return tuple(reversed(selected)), truncated


def message_blocks(message: dict[str, Any], *, default_role: str) -> tuple[ContentBlock, ...]:
    role = str(message.get("role") or default_role)
    content = message.get("content")
    if isinstance(content, str):
        item = block(role, "message", content)
        return (item,) if item else ()
    if not isinstance(content, list):
        return ()
    result: list[ContentBlock] = []
    for raw in content:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("type")
        item: ContentBlock | None = None
        if kind in {"text", "input_text", "output_text"}:
            item = block(role, "message", raw.get("text"))
        elif kind == "thinking":
            item = block(role, "reasoning", raw.get("thinking"), label="thinking")
        elif kind == "tool_use":
            item = block(
                role,
                "tool_call",
                raw.get("input"),
                label=str(raw.get("name") or "tool"),
                call_id=str(raw.get("id") or ""),
            )
        elif kind == "tool_result":
            item = block(
                role,
                "tool_result",
                raw.get("content"),
                label=str(raw.get("tool_use_id") or "tool result"),
                call_id=str(raw.get("tool_use_id") or ""),
            )
        if item:
            result.append(item)
    return tuple(result)
