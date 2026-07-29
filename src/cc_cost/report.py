from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cc_cost.analysis import SessionAnalysis
from cc_cost.interactive_report import render_interactive_html

COMPONENTS = (
    ("cache_read", "cache read"),
    ("cache_write", "cache write"),
    ("output", "output"),
    ("input", "input"),
    ("subagent", "subagents"),
)


def format_usd(usd: Decimal) -> str:
    if usd >= 1:
        return f"${usd:.2f}"
    cents = usd * 100
    if cents >= 10:
        return f"{cents:.0f}c"
    if cents >= 1:
        return f"{cents:.1f}c"
    return "<1c" if cents > 0 else "0c"


def terminal_report(analysis: SessionAnalysis) -> str:
    root = analysis.graph.root
    visible = tuple(turn for turn in analysis.turns if turn.turn.steps)
    hidden = len(analysis.turns) - len(visible)
    interrupted = sum(turn.turn.interrupted for turn in visible)
    turn_notes = []
    if hidden:
        turn_notes.append(f"+{hidden} empty/interrupted hidden")
    if interrupted:
        turn_notes.append(f"{interrupted} interrupted")
    lines = [
        f"provider   : {root.provider}",
        f"transcript : {root.path}",
        f"turns      : {len(visible)}"
        + (f"  ({', '.join(turn_notes)})" if turn_notes else ""),
        f"steps      : {len(root.steps)}"
        + (f"  (+{analysis.subagent_steps} subagent)" if analysis.subagent_steps else ""),
        f"total cost : {format_usd(analysis.total_cost.total)}",
        "by component:",
    ]
    total = analysis.total_cost.total
    own = analysis.own_cost
    values = {
        "cache_read": own.cache_read,
        "cache_write": own.cache_write,
        "output": own.output,
        "input": own.input,
        "subagent": analysis.subagent_cost.total,
    }
    for key, label in COMPONENTS:
        value = values[key]
        if key == "subagent" and not value:
            continue
        share = value / total * 100 if total else Decimal(0)
        lines.append(f"  {label:<12}{format_usd(value):>8}  ({share:4.1f}%)")
    lines.extend(["", f"{'turn':>4} {'steps':>6} {'cost':>8} {'$/step':>8}"])
    for item in visible:
        steps = len(item.turn.steps)
        cost = item.total_cost.total
        per_step = cost / steps if steps else Decimal(0)
        lines.append(
            f"{item.turn.number:>4} {steps:>6} "
            f"{format_usd(cost):>8} {format_usd(per_step):>8}"
        )
    return "\n".join(lines)


def render_html(analysis: SessionAnalysis, path: Path) -> None:
    render_interactive_html(analysis, path)
