"""Run the evaluation over a dataset, save the run record and print the report.

Usage:
    python -m invoice_extractor.evaluate [--dataset ground_truth|ground_truth_real]
        [--path a|b|compare] [--spend-cap USD] [--max-concurrency N] [--prompt v1]

`--path compare` runs both ingestion paths over the same documents and prints the comparison. Each
run writes `runs/<run_id>.json` and `.jsonl` (runs over the real set go to the git-ignored
`runs/real/`); re-render any of them without the model with `python -m invoice_extractor.report_cli`.

Exit codes: 0 reported, 2 usage or configuration error, 3 stopped by the spend cap (partial record saved).
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import TextIO

import anthropic
from dotenv import load_dotenv

from invoice_extractor.client import ModelClient
from invoice_extractor.config import ConfigError, load_config
from invoice_extractor.evaluation.execute import execute
from invoice_extractor.evaluation.manifest import REAL_DIR, SYNTHETIC_DIR, load_manifest
from invoice_extractor.evaluation.path_comparison import compare_paths, compare_records, render_comparison_terminal
from invoice_extractor.evaluation.report import build_report, render_terminal
from invoice_extractor.evaluation.run_record import RUNS_DIR, RunRecord, make_run_id, runs_dir, write_run_record
from invoice_extractor.extraction import UnsupportedInputError
from invoice_extractor.prompts import PromptNotFoundError, load_prompt

EXIT_OK, EXIT_USAGE, EXIT_INCOMPLETE = 0, 2, 3
DEFAULT_SPEND_CAP = Decimal("5.00")
DEFAULT_MAX_CONCURRENCY = 3

DATASETS: dict[str, Path] = {"ground_truth": SYNTHETIC_DIR, "ground_truth_real": REAL_DIR}


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_USAGE


def main(
    argv: Sequence[str] | None = None,
    *,
    client: ModelClient | None = None,
    out: TextIO = sys.stdout,
    runs_root: Path = RUNS_DIR,
    dataset_dirs: Mapping[str, Path] = DATASETS,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m invoice_extractor.evaluate", description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="ground_truth")
    parser.add_argument("--path", choices=["a", "b", "compare"], default="a", help="ingestion path (default a)")
    parser.add_argument("--spend-cap", type=Decimal, default=DEFAULT_SPEND_CAP, help="USD per run (default 5.00)")
    parser.add_argument("--max-concurrency", type=int, default=DEFAULT_MAX_CONCURRENCY)
    parser.add_argument("--prompt", default="v1", help="prompt version under prompts/extract_invoice/")
    args = parser.parse_args(argv)

    if args.spend_cap <= 0:
        return _error("--spend-cap must be positive: a run cannot spend without a limit")
    if args.max_concurrency < 1:
        return _error("--max-concurrency must be at least 1")
    if args.dataset == "ground_truth_real" and args.path == "compare":
        return _error("--path compare is only defined for the synthetic set: the real set is JPG, which path B cannot read")

    dataset_kind = "real" if args.dataset == "ground_truth_real" else "synthetic"
    try:
        prompt = load_prompt(args.prompt)
        manifest = load_manifest(dataset_dirs[args.dataset])
        if client is None:
            load_dotenv()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ConfigError("ANTHROPIC_API_KEY is not set; copy .env.example to .env and fill it in")
            client = ModelClient.from_config(load_config())
        limits = dict(max_concurrency=args.max_concurrency, spend_cap_usd=args.spend_cap)
        if args.path == "compare":
            run_a, run_b = asyncio.run(compare_paths(manifest, client, prompt, **limits))
            records = [run_a] if run_b is None else [run_a, run_b]
        else:
            records = [asyncio.run(execute(manifest, client, prompt, ingestion_path=args.path, **limits))]
    except (ConfigError, PromptNotFoundError, UnsupportedInputError, FileNotFoundError, anthropic.AnthropicError) as exc:
        return _error(f"{type(exc).__name__}: {exc}")

    directory = runs_dir(dataset_kind, runs_root)
    saved: list[tuple[RunRecord, str]] = []
    for record in records:
        run_id = make_run_id(record.config)
        meta_path, _ = write_run_record(directory, run_id, record)
        print(f"run record: {meta_path}", file=out)
        saved.append((record, run_id))

    incomplete = [(r, run_id) for r, run_id in saved if not r.config.complete]
    for record, run_id in incomplete:
        print(
            f"run {run_id} was stopped by its spend cap (${record.config.spend_cap_usd}) after "
            f"{len(record.results)} documents: the partial record is saved and is not reported as a result",
            file=out,
        )
    if incomplete:
        return EXIT_INCOMPLETE

    print(file=out)
    for record, _ in saved:
        print(render_terminal(build_report(record)), file=out)
    if args.path == "compare":
        print(render_comparison_terminal(compare_records(*records)), file=out)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
