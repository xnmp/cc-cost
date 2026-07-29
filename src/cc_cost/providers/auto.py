from __future__ import annotations

from pathlib import Path

from cc_cost.domain import Session
from cc_cost.jsonl import read_jsonl
from cc_cost.providers.claude import parse_claude
from cc_cost.providers.codex import parse_codex


def detect_provider(path: Path) -> str:
    for event in read_jsonl(path):
        event_type = event.get("type")
        if event_type == "session_meta":
            return "codex"
        if event_type in {"user", "assistant"}:
            return "claude"
    raise ValueError(f"cannot detect transcript provider: {path}")


def parse_session(path: Path) -> Session:
    provider = detect_provider(path)
    return parse_codex(path) if provider == "codex" else parse_claude(path)

