import json
from pathlib import Path
from typing import Any

from cc_cost.repository import SessionRepository


def _write(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def _codex_events(
    session_id: str,
    *,
    cwd: str,
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    source: object = "cli"
    thread_source = "user"
    if parent_id:
        source = {
            "subagent": {
                "thread_spawn": {
                    "parent_thread_id": parent_id,
                    "agent_path": f"/root/{session_id}",
                }
            }
        }
        thread_source = "subagent"
    return [
        {
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": cwd,
                "source": source,
                "thread_source": thread_source,
                "timestamp": "2026-01-01T00:00:00Z",
            },
        },
        {"type": "turn_context", "payload": {"model": "gpt-5.6-luna"}},
        {"type": "event_msg", "payload": {"type": "task_started", "started_at": 1}},
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 1,
                    },
                    "last_token_usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 1,
                    },
                },
            },
        },
    ]


def test_codex_discovery_excludes_subagents_and_graph_loads_descendants(
    tmp_path: Path,
) -> None:
    day = tmp_path / ".codex" / "sessions" / "2026" / "01" / "01"
    root = day / "rollout-root.jsonl"
    child = day / "rollout-child.jsonl"
    grandchild = day / "rollout-grandchild.jsonl"
    other = day / "rollout-other.jsonl"
    _write(root, _codex_events("root", cwd="/work"))
    _write(child, _codex_events("child", cwd="/work", parent_id="root"))
    _write(grandchild, _codex_events("grandchild", cwd="/work", parent_id="child"))
    _write(other, _codex_events("other", cwd="/elsewhere"))
    repository = SessionRepository(home=tmp_path)

    assert repository.candidates(Path("/work")) == [root]

    graph = repository.related(root)

    assert set(graph.sessions) == {"root", "child", "grandchild"}
    assert graph.children == {"root": ("child",), "child": ("grandchild",)}
    assert graph.sessions["child"].label == "/root/child"


def test_claude_graph_uses_tool_use_ids(tmp_path: Path) -> None:
    root = tmp_path / ".claude" / "projects" / "-work" / "root.jsonl"
    _write(
        root,
        [
            {"type": "user", "sessionId": "root", "message": {"content": "work"}},
            {
                "type": "assistant",
                "message": {
                    "id": "message",
                    "model": "claude-haiku",
                    "usage": {"output_tokens": 1},
                    "content": [{"type": "tool_use", "id": "tool-1"}],
                },
            },
        ],
    )
    subagents = root.with_suffix("") / "subagents"
    meta = subagents / "agent-a.meta.json"
    transcript = subagents / "agent-a.jsonl"
    meta.parent.mkdir(parents=True)
    meta.write_text(
        json.dumps({"toolUseId": "tool-1", "description": "review"}),
        encoding="utf-8",
    )
    _write(
        transcript,
        [
            {
                "type": "assistant",
                "message": {
                    "id": "sub-message",
                    "model": "claude-haiku",
                    "usage": {"output_tokens": 2},
                },
            }
        ],
    )

    graph = SessionRepository(home=tmp_path).related(root)

    assert graph.children == {"root": ("tool-1",)}
    assert graph.sessions["tool-1"].label == "review"
