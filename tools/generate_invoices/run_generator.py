"""Launcher for the generator CLI that works from any working directory.

`python -m generator.cli` only finds the `generator` package when run inside
tools/generate_invoices/. Run this file with the generator's own venv instead:
    tools/generate_invoices/.venv/Scripts/python tools/generate_invoices/run_generator.py checklist A01
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generator.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
