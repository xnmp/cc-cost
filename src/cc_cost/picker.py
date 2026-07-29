from __future__ import annotations

import os
import select
import shutil
import sys
import termios
import tty
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from cc_cost.domain import Provider


@dataclass(frozen=True, slots=True)
class SessionSummary:
    path: Path
    provider: Provider
    title: str
    modified_at: float
    size: int
    running: bool = False


@dataclass(frozen=True, slots=True)
class PickerState:
    sessions: tuple[SessionSummary, ...]
    query: str = ""
    selected: int = 0

    @property
    def matches(self) -> tuple[SessionSummary, ...]:
        terms = self.query.casefold().split()
        return tuple(
            session
            for session in self.sessions
            if all(term in session.title.casefold() for term in terms)
        )

    def with_query(self, query: str) -> PickerState:
        return replace(self, query=query, selected=0)

    def moved(self, amount: int) -> PickerState:
        count = len(self.matches)
        if not count:
            return replace(self, selected=0)
        return replace(self, selected=max(0, min(self.selected + amount, count - 1)))


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def _age(timestamp: float, *, now: float | None = None) -> str:
    seconds = max(0, int((now or datetime.now(tz=UTC).timestamp()) - timestamp))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    return datetime.fromtimestamp(timestamp, tz=UTC).astimezone().strftime("%Y-%m-%d")


def _size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def render_picker(
    state: PickerState,
    *,
    width: int,
    height: int,
    now: float | None = None,
) -> str:
    matches = state.matches
    page_size = max(1, (height - 7) // 2)
    selected = min(state.selected, max(0, len(matches) - 1))
    page = selected // page_size
    start = page * page_size
    visible = matches[start : start + page_size]
    count = f"{selected + 1} of {len(matches)}" if matches else "0 of 0"
    query = state.query or "Search…"
    lines = [
        f"Resume session ({count})",
        "",
        f"  ⌕ {query}",
        "",
    ]
    if not visible:
        lines.extend(["  No matching sessions", ""])
    for index, session in enumerate(visible, start):
        marker = "❯" if index == selected else " "
        title = _truncate(session.title, max(1, width - 5))
        running = " · running" if session.running else ""
        metadata = (
            f"{_age(session.modified_at, now=now)} · "
            f"{session.provider.title()} · {_size(session.size)}{running}"
        )
        if index == selected:
            metadata = _truncate(metadata, max(1, width - 3))
            lines.append(f"\x1b[7m{marker} {title:<{max(1, width - 3)}}\x1b[0m")
            lines.append(
                f"\x1b[7m  {metadata:<{max(1, width - 3)}}\x1b[0m"
            )
        else:
            lines.extend([f"{marker} {title}", f"  \x1b[2m{metadata}\x1b[0m"])
    lines.extend(
        [
            "",
            "↑/↓ navigate · PgUp/PgDn page · type to search · Enter resume · Esc cancel",
        ]
    )
    return "\r\n".join(_truncate(line, width) if "\x1b" not in line else line for line in lines)


@contextmanager
def _raw_terminal(input_stream: TextIO, output_stream: TextIO) -> Generator[None]:
    descriptor = input_stream.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        output_stream.write("\x1b[?1049h\x1b[?25l")
        output_stream.flush()
        yield
    finally:
        output_stream.write("\x1b[?25h\x1b[?1049l")
        output_stream.flush()
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _read_key(descriptor: int) -> str:
    first = os.read(descriptor, 1)
    if not first:
        return "EOF"
    if first == b"\x1b":
        suffix = b""
        while select.select([descriptor], [], [], 0.02)[0]:
            suffix += os.read(descriptor, 1)
        sequence = first + suffix
        return {
            b"\x1b[A": "UP",
            b"\x1b[B": "DOWN",
            b"\x1b[5~": "PAGE_UP",
            b"\x1b[6~": "PAGE_DOWN",
        }.get(sequence, "ESC")
    if first in {b"\r", b"\n"}:
        return "ENTER"
    if first in {b"\x7f", b"\b"}:
        return "BACKSPACE"
    if first == b"\x03":
        return "ESC"
    byte_count = 1
    if first[0] & 0b11110000 == 0b11110000:
        byte_count = 4
    elif first[0] & 0b11100000 == 0b11100000:
        byte_count = 3
    elif first[0] & 0b11000000 == 0b11000000:
        byte_count = 2
    remaining = os.read(descriptor, byte_count - 1) if byte_count > 1 else b""
    return (first + remaining).decode("utf-8", errors="ignore")


def pick_session(sessions: Sequence[SessionSummary]) -> Path:
    state = PickerState(tuple(sessions))
    stream = sys.stdout
    descriptor = sys.stdin.fileno()
    with _raw_terminal(sys.stdin, stream):
        while True:
            terminal = shutil.get_terminal_size((100, 24))
            stream.write("\x1b[H\x1b[2J")
            stream.write(
                render_picker(state, width=terminal.columns, height=terminal.lines)
            )
            stream.flush()
            key = _read_key(descriptor)
            page_size = max(1, (terminal.lines - 7) // 2)
            if key == "UP":
                state = state.moved(-1)
            elif key == "DOWN":
                state = state.moved(1)
            elif key == "PAGE_UP":
                state = state.moved(-page_size)
            elif key == "PAGE_DOWN":
                state = state.moved(page_size)
            elif key == "BACKSPACE":
                state = state.with_query(state.query[:-1])
            elif key == "ENTER" and state.matches:
                return state.matches[state.selected].path
            elif key in {"ESC", "EOF"}:
                raise KeyboardInterrupt
            elif key.isprintable():
                state = state.with_query(state.query + key)
