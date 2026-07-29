from datetime import UTC, datetime
from pathlib import Path

from cc_cost.analysis import CostAnalyzer
from cc_cost.chart import build_chart
from cc_cost.domain import Session, Step, TokenUsage, Turn
from cc_cost.repository import SessionGraph


def test_chart_preserves_turn_step_and_subagent_drilldown_contract() -> None:
    root = Session(
        id="root",
        provider="codex",
        path=Path("/root.jsonl"),
        cwd=Path("/work"),
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        turns=(
            Turn(
                1,
                (
                    Step("gpt-5.6-sol", TokenUsage(input=1_000_000)),
                    Step("gpt-5.6-sol", TokenUsage(output=1_000_000)),
                ),
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
    )
    child = Session(
        id="child",
        provider="codex",
        path=Path("/child.jsonl"),
        cwd=Path("/work"),
        started_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        parent_id="root",
        label="/root/review",
        turns=(
            Turn(1, (Step("gpt-5.6-terra", TokenUsage(input=1_000_000)),)),
        ),
    )
    graph = SessionGraph(
        root=root,
        sessions={"root": root, "child": child},
        children={"root": ("child",)},
    )
    analysis = CostAnalyzer(graph).analyze()

    nodes, colors, models = build_chart(
        analysis,
        ("color-1", "color-2", "color-3"),
    )

    assert set(nodes) == {"root", "root_steps", "child"}
    assert nodes["root"]["kind"] == "turn"
    assert nodes["root_steps"]["kind"] == "step"
    assert len(nodes["root"]["bars"]) == 1
    assert len(nodes["root_steps"]["bars"]) == 2
    assert nodes["root"]["bars"][0]["subs"][0]["id"] == "child"
    assert nodes["root_steps"]["bars"][1]["subs"][0]["id"] == "child"
    assert nodes["child"]["subtitle"] == "/root/review"
    assert nodes["root"]["total"] == 37.5
    assert models == ("GPT-5.6 Sol", "GPT-5.6 Terra")
    assert colors == {"GPT-5.6 Sol": "color-1", "GPT-5.6 Terra": "color-2"}
