import json
from pathlib import Path
from typing import Any

from cc_cost.providers.codex import parse_codex


def _write(path: Path, events: list[dict[str, Any]], malformed: bool = False) -> None:
    text = "\n".join(json.dumps(event) for event in events)
    if malformed:
        text += "\n{partial"
    path.write_text(text + "\n", encoding="utf-8")


def _token(total: tuple[int, int, int, int], last: tuple[int, int, int, int]) -> dict:
    def usage(values: tuple[int, int, int, int]) -> dict[str, int]:
        return {
            "input_tokens": values[0],
            "cached_input_tokens": values[1],
            "cache_write_input_tokens": values[2],
            "output_tokens": values[3],
        }

    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {"total_token_usage": usage(total), "last_token_usage": usage(last)},
        },
    }


def test_codex_uses_cumulative_deltas_and_deduplicates_snapshots(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {
            "type": "session_meta",
            "payload": {
                "id": "root",
                "cwd": "/work",
                "timestamp": "2026-01-01T00:00:00Z",
                "source": "cli",
            },
        },
        {
            "type": "turn_context",
            "payload": {"model": "gpt-5.6-sol", "turn_id": "turn-1"},
        },
        {
            "type": "event_msg",
            "payload": {"type": "task_started", "started_at": 1_767_225_600},
        },
        _token((100, 40, 10, 5), (100, 40, 10, 5)),
        _token((100, 40, 10, 5), (100, 40, 10, 5)),
        _token((180, 60, 10, 12), (80, 20, 0, 7)),
        {
            "type": "event_msg",
            "payload": {"type": "task_complete", "completed_at": 1_767_225_601},
        },
    ]
    _write(path, events, malformed=True)

    session = parse_codex(path)

    assert session.id == "root"
    assert session.cwd == Path("/work")
    assert len(session.turns) == 1
    assert len(session.steps) == 2
    assert session.steps[0].usage.input == 50  # 100 total - 40 cached - 10 write
    assert session.steps[0].usage.cache_read == 40
    assert session.steps[0].usage.cache_write_5m == 10
    assert session.steps[1].usage.input == 60
    assert session.steps[1].usage.output == 7


def test_codex_attributes_active_model_per_turn_and_keeps_live_turn(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "root", "source": "cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
        {"type": "event_msg", "payload": {"type": "task_started", "started_at": 1}},
        _token((10, 0, 0, 2), (10, 0, 0, 2)),
        {"type": "event_msg", "payload": {"type": "turn_aborted", "completed_at": 2}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-luna"}},
        {"type": "event_msg", "payload": {"type": "task_started", "started_at": 3}},
        _token((25, 5, 0, 3), (15, 5, 0, 1)),
    ]
    _write(path, events)

    session = parse_codex(path)

    assert [turn.interrupted for turn in session.turns] == [True, False]
    assert session.turns[0].steps[0].model == "gpt-5.6-terra"
    assert session.turns[1].steps[0].model == "gpt-5.6-luna"
    assert session.turns[1].steps[0].usage.input == 10


def test_codex_falls_back_to_last_usage_if_cumulative_counter_resets(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "root", "source": "cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
        {"type": "event_msg", "payload": {"type": "task_started"}},
        _token((100, 50, 0, 5), (100, 50, 0, 5)),
        _token((20, 10, 0, 2), (20, 10, 0, 2)),
    ]
    _write(path, events)

    session = parse_codex(path)

    assert len(session.steps) == 2
    assert session.steps[1].usage.input == 10
    assert session.steps[1].usage.cache_read == 10
