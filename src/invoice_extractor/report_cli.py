"""Re-render a saved run as a report, or two saved runs as a path comparison. Never calls the model.

Usage:
    python -m invoice_extractor.report_cli <run_id> [--dataset runs|runs/real]
        [--compare-with <path-B run_id>] [--markdown out.md]

Exit codes: 0 rendered, 2 usage error (unknown run, unreadable record), 3 the run is incomplete.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from invoice_extractor.evaluation.path_comparison import (
    compare_records,
    render_comparison_markdown,
    render_comparison_terminal,
)
from invoice_extractor.evaluation.report import build_report, render_markdown, render_terminal
from invoice_extractor.evaluation.run_record import (
    REAL_RUNS_DIRNAME,
    RUNS_DIR,
    IncompleteRunError,
    read_run_record,
)

EXIT_OK, EXIT_USAGE, EXIT_INCOMPLETE = 0, 2, 3


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: Sequence[str] | None = None, *, out: TextIO = sys.stdout, runs_root: Path = RUNS_DIR) -> int:
    parser = argparse.ArgumentParser(prog="python -m invoice_extractor.report_cli", description=__doc__.splitlines()[0])
    parser.add_argument("run_id")
    parser.add_argument("--dataset", choices=["runs", "runs/real"], default="runs")
    parser.add_argument("--compare-with", metavar="RUN_ID", help="the path B run to compare the given path A run with")
    parser.add_argument("--markdown", type=Path, metavar="FILE", help="also write the report as markdown")
    args = parser.parse_args(argv)

    directory = runs_root / REAL_RUNS_DIRNAME if args.dataset == "runs/real" else runs_root
    try:
        record = read_run_record(directory, args.run_id)
        other = read_run_record(directory, args.compare_with) if args.compare_with else None
    except FileNotFoundError as exc:
        return _error(f"no such run record: {exc.filename}")
    except (ValueError, ValidationError) as exc:  # a corrupt record, or one whose aggregates disagree with its documents
        return _error(f"unreadable run record: {exc}")

    try:
        report = build_report(record)
        comparison = compare_records(record, other) if other is not None else None
        if other is not None:
            build_report(other)  # an incomplete path B run is refused too
    except IncompleteRunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INCOMPLETE
    except ValueError as exc:
        return _error(str(exc))

    print(render_terminal(report), file=out)
    if comparison is not None:
        print(render_comparison_terminal(comparison), file=out)
    if args.markdown:
        markdown = render_markdown(report)
        if comparison is not None:
            markdown += "\n" + render_comparison_markdown(comparison)
        args.markdown.write_text(markdown, encoding="utf-8", newline="\n")
        print(f"markdown written to {args.markdown}", file=out)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
