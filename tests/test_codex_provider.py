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


def test_codex_uses_last_request_usage_and_deduplicates_snapshots(tmp_path: Path) -> None:
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
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "inspect this pass"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "First response"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "read_file",
                "arguments": '{"path":"/tmp/example.py","line":12}',
            },
        },
        _token((100, 40, 10, 5), (100, 40, 10, 5)),
        _token((100, 40, 10, 5), (100, 40, 10, 5)),
        {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Second response"},
        },
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
    assert session.steps[0].trace.input[0].text == "inspect this pass"
    assert session.steps[0].trace.output[0].text == "First response"
    assert session.steps[0].trace.output[1].label == "read_file"
    assert session.steps[0].trace.output[1].text == (
        '{\n  "path": "/tmp/example.py",\n  "line": 12\n}'
    )


def test_codex_attributes_active_model_per_turn_and_keeps_live_turn(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "root", "source": "cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
        {"type": "event_msg", "payload": {"type": "task_started", "started_at": 1}},
        {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Terra response"},
        },
        _token((10, 0, 0, 2), (10, 0, 0, 2)),
        {"type": "event_msg", "payload": {"type": "turn_aborted", "completed_at": 2}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-luna"}},
        {"type": "event_msg", "payload": {"type": "task_started", "started_at": 3}},
        {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Luna response"},
        },
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
        {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Before reset"},
        },
        _token((100, 50, 0, 5), (100, 50, 0, 5)),
        {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "After reset"},
        },
        _token((20, 10, 0, 2), (20, 10, 0, 2)),
    ]
    _write(path, events)

    session = parse_codex(path)

    assert len(session.steps) == 2
    assert session.steps[1].usage.input == 10
    assert session.steps[1].usage.cache_read == 10


def test_codex_ignores_child_accounting_updates_without_local_responses(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "root", "source": "cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
        {"type": "event_msg", "payload": {"type": "task_started"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Review this"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "message": "I am reviewing it.",
                "phase": "commentary",
            },
        },
        _token((100, 40, 0, 10), (100, 40, 0, 10)),
        _token((500, 300, 0, 50), (400, 260, 0, 40)),
        _token((900, 600, 0, 90), (400, 300, 0, 40)),
        {
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "message": "The review is complete.",
                "phase": "final_answer",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "The review is complete."}],
            },
        },
        _token((1_000, 650, 0, 100), (100, 50, 0, 10)),
    ]
    _write(path, events)

    steps = parse_codex(path).steps

    assert len(steps) == 2
    assert steps[0].usage.total == 110
    assert steps[0].trace.input[0].text == "Review this"
    assert steps[0].trace.output[0].text == "I am reviewing it."
    assert steps[1].usage.total == 110
    assert [item.text for item in steps[1].trace.input] == [
        "Review this",
        "I am reviewing it.",
    ]
    assert [item.text for item in steps[1].trace.output] == ["The review is complete."]


def test_codex_preserves_current_tool_and_agent_content_in_pass_traces(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "root", "source": "cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
        {"type": "event_msg", "payload": {"type": "task_started"}},
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": "call-1",
                "input": "*** Begin Patch\nhuge edit\n*** End Patch",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-1",
                "output": "Success. Updated one file.",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "tool_search_call",
                "call_id": "call-2",
                "arguments": {"query": "calendar tools"},
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "tool_search_output",
                "call_id": "call-2",
                "tools": [{"name": "search_events", "description": "Search events"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "agent_message",
                "author": "/root/reviewer",
                "recipient": "/root",
                "content": [{"type": "input_text", "text": "Review passed."}],
            },
        },
        _token((100, 40, 0, 10), (100, 40, 0, 10)),
    ]
    _write(path, events)

    step = parse_codex(path).steps[0]

    assert [(item.kind, item.label) for item in step.trace.output] == [
        ("tool_call", "apply_patch"),
        ("tool_call", "tool search"),
    ]
    assert [item.call_id for item in step.trace.output] == ["call-1", "call-2"]
    assert step.trace.output[0].text == "*** Begin Patch\nhuge edit\n*** End Patch"
    assert json.loads(step.trace.output[1].text) == {"query": "calendar tools"}
    assert [(item.kind, item.label) for item in step.trace.input] == [
        ("tool_result", "call-1"),
        ("tool_result", "call-2"),
        ("message", ""),
    ]
    assert [item.call_id for item in step.trace.input] == ["call-1", "call-2", ""]
    assert step.trace.input[0].text == "Success. Updated one file."
    assert json.loads(step.trace.input[1].text) == [
        {"name": "search_events", "description": "Search events"}
    ]
    assert step.trace.input[2].text == "Review passed."


def test_codex_ignores_unreadable_and_malformed_response_items_without_losing_usage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollout.jsonl"
    events: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": "root", "source": "cli"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
        {"type": "event_msg", "payload": {"type": "task_started"}},
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "encrypted_content", "encrypted_content": "secret"}],
            },
        },
        {"type": "response_item", "payload": {"type": "custom_tool_call"}},
        {"type": "response_item", "payload": {"type": "agent_message", "content": None}},
        _token((50, 20, 0, 5), (50, 20, 0, 5)),
    ]
    _write(path, events, malformed=True)

    step = parse_codex(path).steps[0]

    assert step.usage.total == 55
    assert step.trace.input == ()
    assert step.trace.output == ()
