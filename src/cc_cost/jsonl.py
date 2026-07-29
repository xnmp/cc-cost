from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


def read_jsonl(path: Path) -> Iterator[JsonObject]:
    """Yield valid JSON objects; tolerate partial live-session lines."""
    with path.open(encoding="utf-8") as transcript:
        for line in transcript:
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(value, dict):
                yield value


def read_json(path: Path) -> JsonObject | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None

