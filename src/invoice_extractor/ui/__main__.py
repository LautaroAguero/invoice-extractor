"""Launch the page: `python -m invoice_extractor.ui`.

Streamlit runs a script rather than importing a module, so this hands `app.py` to its CLI.
Extra arguments pass through (`--server.port 8502`, for example).
"""

import sys
from pathlib import Path

APP = Path(__file__).resolve().parent / "app.py"


def main(argv: list[str] | None = None) -> int:
    try:
        from streamlit.web import cli as streamlit_cli
    except ModuleNotFoundError:
        print(
            "streamlit no está instalado. Instalá el extra de la interfaz:\n    pip install -e .[ui]",
            file=sys.stderr,
        )
        return 2
    sys.argv = ["streamlit", "run", str(APP), *(argv if argv is not None else sys.argv[1:])]
    return streamlit_cli.main()


if __name__ == "__main__":
    raise SystemExit(main())
