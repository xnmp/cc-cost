from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from cc_cost.analysis import CostAnalyzer
from cc_cost.domain import Session, Step, TokenUsage, Turn
from cc_cost.repository import SessionGraph


def _session(
    session_id: str,
    *,
    parent_id: str | None = None,
    started_at: datetime | None = None,
    turns: tuple[Turn, ...] | None = None,
) -> Session:
    return Session(
        id=session_id,
        provider="codex",
        path=Path(f"/{session_id}.jsonl"),
        cwd=Path("/work"),
        started_at=started_at,
        parent_id=parent_id,
        turns=turns
        or (Turn(1, (Step("gpt-5.6-luna", TokenUsage(input=1_000_000)),)),),
    )


def test_analysis_rolls_nested_subagents_into_the_spawning_turn() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    root = _session(
        "root",
        started_at=start,
        turns=(
            Turn(
                1,
                (Step("gpt-5.6-luna", TokenUsage(input=1_000_000)),),
                started_at=start,
            ),
            Turn(
                2,
                (Step("gpt-5.6-luna", TokenUsage(output=1_000_000)),),
                started_at=start + timedelta(minutes=10),
            ),
        ),
    )
    child = _session("child", parent_id="root", started_at=start + timedelta(minutes=12))
    grandchild = _session(
        "grandchild", parent_id="child", started_at=start + timedelta(minutes=13)
    )
    graph = SessionGraph(
        root=root,
        sessions={"root": root, "child": child, "grandchild": grandchild},
        children={"root": ("child",), "child": ("grandchild",)},
    )

    result = CostAnalyzer(graph).analyze()

    assert result.turns[0].subagent_cost.total == 0
    assert result.turns[1].subagent_cost.total == Decimal("2")
    assert result.turns[1].subagent_steps == 2
    assert result.own_cost.total == Decimal("7")
    assert result.total_cost.total == Decimal("9")


def test_analysis_uses_spawn_id_before_timestamp_for_claude_style_graph() -> None:
    root = Session(
        id="root",
        provider="claude",
        path=Path("/root.jsonl"),
        cwd=None,
        started_at=None,
        turns=(
            Turn(
                1,
                (
                    Step(
                        "claude-haiku",
                        TokenUsage(input=1),
                        spawn_ids=("child",),
                    ),
                ),
            ),
            Turn(2, (Step("claude-haiku", TokenUsage(input=1)),)),
        ),
    )
    child = Session(
        id="child",
        provider="claude",
        path=Path("/child.jsonl"),
        cwd=None,
        started_at=None,
        turns=(Turn(1, (Step("claude-haiku", TokenUsage(input=1)),)),),
    )
    graph = SessionGraph(
        root=root,
        sessions={"root": root, "child": child},
        children={"root": ("child",)},
    )

    result = CostAnalyzer(graph).analyze()

    assert result.turns[0].subagent_steps == 1
    assert result.turns[1].subagent_steps == 0

