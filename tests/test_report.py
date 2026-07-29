import json
import re
import shutil
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cc_cost.analysis import CostAnalyzer
from cc_cost.domain import ContentBlock, PassTrace, Session, Step, TokenUsage, Turn
from cc_cost.interactive_report import render_interactive_html
from cc_cost.report import render_html, terminal_report
from cc_cost.repository import SessionGraph
from cc_cost.theme import TerminalTheme


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
                (
                    Step(
                        "gpt-5.6-sol",
                        TokenUsage(input=1_000_000),
                        trace=PassTrace(
                            input=(
                                ContentBlock(
                                    "user",
                                    "message",
                                    "Explain the selected tokens",
                                ),
                                ContentBlock(
                                    "tool",
                                    "tool_result",
                                    "File contents",
                                    label="call-1",
                                    call_id="call-1",
                                ),
                            ),
                            output=(
                                ContentBlock(
                                    "assistant",
                                    "message",
                                    "Here is the explanation",
                                ),
                                ContentBlock(
                                    "assistant",
                                    "tool_call",
                                    '{\n  "outer": {\n    "inner": 1\n  }\n}',
                                    label="inspect_json",
                                    call_id="call-1",
                                ),
                            ),
                        ),
                    ),
                ),
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
    assert "passes     : 1" in text
    assert "$/pass" in text
    assert "total cost : $5.00" in text
    assert "Session cost by turn" in document
    assert '"total": 5.0' in document
    assert 'id="perstep"' in document
    assert 'id="norm"' in document
    assert 'id="subs"' in document
    assert "buildMini" in document
    assert "openAgent" in document
    assert "per-pass bars" in document
    assert "normalize by passes" in document
    assert 'input:"uncached input"' in document
    assert "Explain the selected tokens" in document
    assert "Readable transcript content associated" in document
    assert 'id="inspect"' in document
    assert 'data-comp="' in document
    assert "width: min(1180px" in document
    assert ".trace.user" in document
    assert ".trace.assistant" in document
    assert "function jsonTree" in document
    assert "function traceMarkup" in document
    assert "function inspectionBlocks" in document
    assert "function toolExchangeMarkup" in document
    assert '<details class="trace tool">' in document
    assert "inspect_json" in document
    assert '"call_id": "call-1"' in document
    assert "Arguments" in document
    assert "Result" in document


def test_html_escapes_script_closing_sequences_in_session_labels(tmp_path: Path) -> None:
    session = Session(
        id="root",
        provider="codex",
        path=Path("/transcript.jsonl"),
        cwd=Path("/work"),
        started_at=None,
        label="</script><script>alert(1)</script>",
        turns=(
            Turn(
                1,
                (
                    Step(
                        "gpt-5.6-sol",
                        TokenUsage(input=1),
                        trace=PassTrace(
                            input=(
                                ContentBlock(
                                    "user",
                                    "message",
                                    "</script><script>alert('trace')</script>",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    analysis = CostAnalyzer(
        SessionGraph(root=session, sessions={"root": session}, children={})
    ).analyze()
    output = tmp_path / "report.html"
    theme = replace(
        TerminalTheme.system(),
        name="</script><script>alert(1)</script>",
    )

    render_interactive_html(analysis, output, theme=theme)
    document = output.read_text(encoding="utf-8")

    assert document.count("</script>") == 1
    assert "\\u003c/script\\u003e" in document


def test_generated_javascript_parses(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for generated JavaScript validation")
    session = Session(
        id="root",
        provider="codex",
        path=Path("/transcript.jsonl"),
        cwd=Path("/work"),
        started_at=None,
        turns=(Turn(1, (Step("gpt-5.6-sol", TokenUsage(input=1)),)),),
    )
    analysis = CostAnalyzer(
        SessionGraph(root=session, sessions={"root": session}, children={})
    ).analyze()
    output = tmp_path / "report.html"
    script = tmp_path / "report.js"
    render_interactive_html(analysis, output, theme=TerminalTheme.system())
    document = output.read_text(encoding="utf-8")
    match = re.search(r"<script>([\s\S]+)</script>", document)
    assert match is not None
    script.write_text(match.group(1), encoding="utf-8")

    result = subprocess.run(
        [node, "--check", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_generated_patch_renderer_formats_multi_file_malformed_and_huge_inputs(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for generated JavaScript validation")
    session = Session(
        id="root",
        provider="codex",
        path=Path("/transcript.jsonl"),
        cwd=Path("/work"),
        started_at=None,
        turns=(Turn(1, (Step("gpt-5.6-sol", TokenUsage(input=1)),)),),
    )
    analysis = CostAnalyzer(
        SessionGraph(root=session, sessions={"root": session}, children={})
    ).analyze()
    output = tmp_path / "report.html"
    script = tmp_path / "report.cjs"
    render_interactive_html(analysis, output, theme=TerminalTheme.system())
    document = output.read_text(encoding="utf-8")
    match = re.search(r"<script>([\s\S]+)</script>", document)
    assert match is not None
    script.write_text(match.group(1), encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: src/a.py
@@
-old <value>
+new <value>
*** Add File: src/b.py
+created
*** End Patch"""
    program = f"""
const renderer=require({json.dumps(str(script))});
const html=renderer.patchContent({json.dumps(patch)});
const malformed=renderer.patchContent("*** Begin Patch\\nunknown\\n*** End Patch");
const huge=renderer.patchContent(
  "*** Begin Patch\\n*** Add File: huge.txt\\n+"+
  "x".repeat(100000)+"\\n*** End Patch"
);
console.log(JSON.stringify({{
  files:(html.match(/class="pline file"/g)||[]).length,
  additions:(html.match(/class="pline add"/g)||[]).length,
  deletions:(html.match(/class="pline delete"/g)||[]).length,
  escaped:html.includes("&lt;value&gt;"),
  malformed:malformed.includes("<b>0 files</b>"),
  huge:huge.length>100000&&huge.includes("<b>1 file</b>")
}}));
"""

    result = subprocess.run(
        [node, "-e", program],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "files": 2,
        "additions": 2,
        "deletions": 1,
        "escaped": True,
        "malformed": True,
        "huge": True,
    }
