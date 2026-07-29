from datetime import UTC, datetime
from pathlib import Path

from cc_cost.picker import PickerState, SessionSummary, render_picker

NOW = datetime(2026, 7, 30, tzinfo=UTC).timestamp()


def _session(number: int, title: str) -> SessionSummary:
    return SessionSummary(
        path=Path(f"/session-{number}.jsonl"),
        provider="codex" if number % 2 else "claude",
        title=title,
        modified_at=NOW - number * 3600,
        size=number * 1024,
    )


def test_search_matches_session_titles_case_insensitively() -> None:
    state = PickerState(
        (
            _session(1, "Fix session resume picker"),
            _session(2, "Review pricing model"),
            _session(3, "Picker accessibility follow-up"),
        )
    ).with_query("PICKER follow")

    assert [session.title for session in state.matches] == [
        "Picker accessibility follow-up"
    ]


def test_picker_pages_over_the_full_session_list() -> None:
    sessions = tuple(_session(index, f"Session {index}") for index in range(1, 31))
    state = PickerState(sessions).moved(12)

    screen = render_picker(state, width=80, height=15, now=NOW)

    assert "Resume session (13 of 30)" in screen
    assert "Session 13" in screen
    assert "Session 1\r\n" not in screen
    assert "Session 30" not in screen


def test_picker_renders_human_title_and_session_metadata() -> None:
    state = PickerState((_session(2, "Add searchable session names"),))

    screen = render_picker(state, width=80, height=24, now=NOW)

    assert "Add searchable session names" in screen
    assert "2h ago · Claude · 2.0KB" in screen
    assert "session-2" not in screen
    assert "type to search" in screen
