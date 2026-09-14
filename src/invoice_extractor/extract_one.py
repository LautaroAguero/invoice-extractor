"""Extract one PDF and print what the call cost and how it ended.

Usage:
    python -m invoice_extractor.extract_one <pdf> [--max-tokens N] [--prompt v1]

Exit codes: 0 extracted, 1 explicit failure (model failure or call failure), 2 usage or configuration error.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

import anthropic
from dotenv import load_dotenv

from invoice_extractor.client import CallFailure, ModelClient
from invoice_extractor.config import ConfigError, load_config
from invoice_extractor.extraction import ExtractionRecord, UnsupportedInputError, extract_document
from invoice_extractor.prompts import PromptNotFoundError, load_prompt
from invoice_extractor.schema import Extracted

EXIT_EXTRACTED, EXIT_FAILURE, EXIT_USAGE = 0, 1, 2


def format_summary(record: ExtractionRecord) -> str:
    call = record.call
    outcome = call.outcome
    if isinstance(outcome, CallFailure):
        outcome_line = f"call failure ({outcome.kind}): {outcome.detail}"
    elif isinstance(outcome.value.result, Extracted):
        outcome_line = "extracted"
    else:
        failed = outcome.value.result
        outcome_line = f"model failure ({failed.reason}): {failed.detail}"
    return "\n".join(
        [
            f"file:        {record.source}",
            f"prompt:      {record.prompt_version}",
            f"model:       {call.model_id}",
            f"tokens:      in {call.input_tokens} | out {call.output_tokens}"
            f" | cache read {call.cache_read_input_tokens} | cache write {call.cache_creation_input_tokens}",
            f"stop reason: {call.stop_reason}",
            f"latency:     {call.latency_ms} ms",
            f"cost:        ${call.cost_usd:.6f}",
            f"request id:  {call.request_id}",
            f"outcome:     {outcome_line}",
        ]
    )


def main(argv: Sequence[str] | None = None, *, client: ModelClient | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m invoice_extractor.extract_one", description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--max-tokens", type=int, default=None, help="override the configured max_tokens")
    parser.add_argument("--prompt", default="v1", help="prompt version under prompts/extract_invoice/")
    args = parser.parse_args(argv)

    try:
        prompt = load_prompt(args.prompt)
        if client is None:
            load_dotenv()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ConfigError("ANTHROPIC_API_KEY is not set; copy .env.example to .env and fill it in")
            client = ModelClient.from_config(load_config())
        record = asyncio.run(extract_document(args.pdf, client=client, prompt=prompt, max_tokens=args.max_tokens))
    except (ConfigError, PromptNotFoundError, UnsupportedInputError, FileNotFoundError, anthropic.AnthropicError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    print(format_summary(record), file=out)
    outcome = record.call.outcome
    if isinstance(outcome, CallFailure):
        return EXIT_FAILURE
    print(outcome.value.model_dump_json(indent=2), file=out)
    return EXIT_EXTRACTED if isinstance(outcome.value.result, Extracted) else EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
