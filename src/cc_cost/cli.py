from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from cc_cost.analysis import CostAnalyzer
from cc_cost.pricing import UnknownModelError
from cc_cost.report import render_html, terminal_report
from cc_cost.repository import SessionRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cc-cost",
        description="Report API-equivalent cost for a Claude Code or Codex session.",
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        type=Path,
        help="Claude Code or Codex JSONL transcript (default: discover from cwd)",
    )
    parser.add_argument("-o", "--output", type=Path, help="HTML report path")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not open the HTML report in a browser",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    repository = SessionRepository()
    path = (
        args.transcript.expanduser().resolve()
        if args.transcript
        else repository.choose(repository.candidates(Path.cwd()))
    )
    if not path.is_file():
        raise FileNotFoundError(f"transcript does not exist: {path}")
    analysis = CostAnalyzer(repository.related(path)).analyze()
    print(terminal_report(analysis))

    output = args.output or (
        Path(tempfile.gettempdir()) / f"cc-cost-{analysis.graph.root.id}.html"
    )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    render_html(analysis, output)
    print(f"\nchart      : {output}")

    configured_open = os.environ.get(
        "CC_COST_OPEN", os.environ.get("SESSION_COST_OPEN", "1")
    )
    if not args.no_open and configured_open == "1":
        with suppress(OSError):
            subprocess.Popen(
                ["xdg-open", str(output)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    return 0


def main() -> None:
    try:
        raise SystemExit(run(_parser().parse_args()))
    except (FileNotFoundError, UnknownModelError, ValueError) as error:
        print(f"cc-cost: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
