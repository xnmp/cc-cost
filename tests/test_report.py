from datetime import UTC, datetime
from pathlib import Path

from cc_cost.analysis import CostAnalyzer
from cc_cost.domain import Session, Step, TokenUsage, Turn
from cc_cost.report import render_html, terminal_report
from cc_cost.repository import SessionGraph


def test_reports_expose_user_visible_totals(tmp_path: Path) -> None:
    session = Session(
        id="<session>",
        provider="codex",
        path=Path("/transcript.jsonl"),
        cwd=Path("/work"),
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        turns=(
            Turn(
                1,
                (Step("gpt-5.6-sol", TokenUsage(input=1_000_000)),),
            ),
        ),
    )
    analysis = CostAnalyzer(
        SessionGraph(root=session, sessions={session.id: session}, children={})
    ).analyze()
    output = tmp_path / "report.html"

    text = terminal_report(analysis)
    render_html(analysis, output)
    document = output.read_text(encoding="utf-8")

    assert "provider   : codex" in text
    assert "total cost : $5.00" in text
    assert "Session cost by turn" in document
    assert "$5.00" in document
    assert "&lt;session&gt;" in document
