import json
from pathlib import Path

from cc_cost.providers.claude import parse_claude


def _write(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def test_claude_deduplicates_streamed_messages_and_unions_spawn_ids(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    events = [
        {
            "type": "user",
            "sessionId": "session-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": "do work"},
        },
        {
            "type": "assistant",
            "message": {
                "id": "message-1",
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 100,
                    "cache_read_input_tokens": 50,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 20,
                        "ephemeral_1h_input_tokens": 30,
                    },
                    "output_tokens": 10,
                },
                "content": [{"type": "text", "text": "Working on it"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "id": "message-1",
                "model": "claude-opus-4-6",
                "usage": {},
                "content": [{"type": "tool_use", "id": "tool-1"}],
            },
        },
    ]
    _write(path, events)

    session = parse_claude(path)

    assert session.id == "session-1"
    assert len(session.steps) == 1
    assert session.steps[0].spawn_ids == ("tool-1",)
    assert session.steps[0].usage.cache_write == 50
    assert session.steps[0].usage.total == 210
    assert session.steps[0].trace.input[0].text == "do work"
    assert session.steps[0].trace.output[0].text == "Working on it"
    assert session.steps[0].trace.cached_preview[0].text == "do work"


def test_claude_excludes_tool_results_as_user_turns_and_synthetic_steps(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    events = [
        {"type": "user", "message": {"content": "prompt"}},
        {
            "type": "assistant",
            "message": {
                "id": "real",
                "model": "claude-sonnet-4-6",
                "usage": {"output_tokens": 1},
            },
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "x"}]},
        },
        {
            "type": "assistant",
            "message": {
                "id": "synthetic",
                "model": "<synthetic>",
                "usage": {"output_tokens": 999},
            },
        },
        {"type": "user", "message": {"content": [{"type": "text", "text": "next"}]}},
    ]
    _write(path, events)

    session = parse_claude(path)

    assert len(session.turns) == 2
    assert len(session.turns[0].steps) == 1
    assert session.turns[1].steps == ()
