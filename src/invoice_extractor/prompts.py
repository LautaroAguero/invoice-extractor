"""Versioned prompt files (CC-6, design D12)."""

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "extract_invoice"
_VERSION_RE = re.compile(r"^v[1-9]\d*$")


class PromptNotFoundError(LookupError):
    """The requested prompt version does not exist. There is no fallback to another version."""


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    text: str


def load_prompt(version: str, prompts_dir: Path = PROMPTS_DIR) -> Prompt:
    if not _VERSION_RE.fullmatch(version):
        raise PromptNotFoundError(f"invalid prompt version {version!r}; expected v1, v2, ...")
    path = prompts_dir / f"{version}.md"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise PromptNotFoundError(f"prompt {version} not found at {path}") from None
    if not text:
        raise PromptNotFoundError(f"prompt {version} at {path} is empty")
    return Prompt(version=version, text=text)
