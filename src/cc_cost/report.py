from __future__ import annotations

import html
import json
from decimal import Decimal
from pathlib import Path

from cc_cost.analysis import SessionAnalysis

COMPONENTS = (
    ("cache_read", "cache read", "#35a99b"),
    ("cache_write", "cache write", "#8b6bd6"),
    ("output", "output", "#5d7fd3"),
    ("input", "input", "#9299a7"),
    ("subagent", "subagents", "#e18a45"),
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
    for key, label, _ in COMPONENTS:
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


def _row(label: str, color: str, value: Decimal, total: Decimal) -> str:
    share = value / total * 100 if total else Decimal(0)
    return (
        '<div class="row"><i style="background:'
        + color
        + '"></i><span>'
        + html.escape(label)
        + "</span><b>"
        + format_usd(value)
        + f'</b><em>{share:.1f}%</em></div>'
    )


def render_html(analysis: SessionAnalysis, path: Path) -> None:
    turns = [item for item in analysis.turns if item.turn.steps]
    maximum = max((item.total_cost.total for item in turns), default=Decimal(1))
    bars: list[str] = []
    for item in turns:
        values = (
            item.own_cost.cache_read,
            item.own_cost.cache_write,
            item.own_cost.output,
            item.own_cost.input,
            item.subagent_cost.total,
        )
        segments = []
        for value, (_, label, color) in zip(values, COMPONENTS, strict=True):
            if not value:
                continue
            width = value / maximum * 100
            segments.append(
                f'<span style="width:{width:.5f}%;background:{color}" '
                f'title="{html.escape(label)} · {format_usd(value)}"></span>'
            )
        bars.append(
            f'<div class="turn"><label>{item.turn.number}</label>'
            f'<div class="track">{"".join(segments)}</div>'
            f"<b>{format_usd(item.total_cost.total)}</b>"
            f'<small>{len(item.turn.steps)} steps'
            + (f" + {item.subagent_steps} subagent" if item.subagent_steps else "")
            + "</small></div>"
        )

    own = analysis.own_cost
    total = analysis.total_cost.total
    breakdown_values = (
        own.cache_read,
        own.cache_write,
        own.output,
        own.input,
        analysis.subagent_cost.total,
    )
    breakdown = "".join(
        _row(label, color, value, total)
        for value, (_, label, color) in zip(breakdown_values, COMPONENTS, strict=True)
        if value
    )
    model_rows = "".join(
        _row(model, "#596273", cost.total, total)
        for model, cost in sorted(
            analysis.costs_by_model.items(), key=lambda item: item[1].total, reverse=True
        )
    )
    metadata = json.dumps(
        {
            "provider": analysis.graph.root.provider,
            "session": analysis.graph.root.id,
            "transcript": str(analysis.graph.root.path),
        }
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>cc-cost · session report</title>
<style>
:root{{--bg:#eef1f5;--panel:#fff;--text:#1b2029;--muted:#697180;--line:#dce1e8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font:14px ui-sans-serif,system-ui,sans-serif;padding:32px 20px}}main{{max-width:980px;margin:auto}}
header{{display:flex;justify-content:space-between;align-items:end;margin-bottom:20px}}
h1{{font-size:22px;margin:0}}header p{{margin:5px 0 0;color:var(--muted)}}.total{{text-align:right}}
.total b{{font-size:34px}}.total span{{display:block;color:var(--muted);font-size:11px;
text-transform:uppercase;letter-spacing:.08em}}.panel{{background:var(--panel);
border:1px solid var(--line);border-radius:14px;padding:18px;
box-shadow:0 10px 30px #2634470c}}h2{{font-size:12px;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted);margin:0 0 16px}}.turn{{display:grid;
grid-template-columns:32px 1fr 68px;gap:10px;align-items:center;margin:11px 0}}
.turn label,.turn b{{font-variant-numeric:tabular-nums}}.turn b{{text-align:right}}.turn small{{
grid-column:2/4;color:var(--muted);margin-top:-8px}}.track{{height:22px;display:flex;border-radius:5px;
overflow:hidden;background:#edf0f4}}.track span{{height:100%;min-width:1px}}.grid{{display:grid;
grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}}.row{{display:grid;
grid-template-columns:12px 1fr 70px 48px;align-items:center;gap:8px;margin:10px 0}}
.row i{{width:11px;height:11px;border-radius:3px}}.row b,.row em{{text-align:right;
font-variant-numeric:tabular-nums}}.row em{{font-style:normal;color:var(--muted)}}
footer{{color:var(--muted);font-size:12px;margin-top:18px;overflow-wrap:anywhere}}
@media(max-width:650px){{.grid{{grid-template-columns:1fr}}header{{align-items:start}}}}
</style></head><body><main><header><div><h1>Session cost by turn</h1>
<p>{html.escape(analysis.graph.root.provider.title())} · {len(turns)} turns ·
{len(analysis.graph.root.steps)} main steps</p></div><div class="total"><b>{format_usd(total)}</b>
<span>API-equivalent spend</span></div></header><section class="panel"><h2>turns</h2>
{"".join(bars) or "<p>No completed model steps found.</p>"}</section><div class="grid">
<section class="panel"><h2>cost breakdown</h2>{breakdown}</section>
<section class="panel"><h2>models</h2>{model_rows}</section></div>
<footer>Generated by cc-cost. Codex values estimate standard API-equivalent token spend;
subscription billing may differ. Data: <code>{html.escape(metadata)}</code></footer>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")
