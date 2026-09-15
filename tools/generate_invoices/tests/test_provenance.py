"""Task 6.5: generation refuses to run on uncommitted generator code (design D9, provenance guard)."""

import subprocess

import pytest

import generator.cli as cli
from generator.manifest import TOOL_ROOT, DirtyTreeError, ensure_clean_generator_tree


def _fake_git(stdout: str = "", error: Exception | None = None):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if error is not None:
            raise error
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    return run, calls


def test_clean_tree_passes_and_scopes_status_to_the_generator():
    run, calls = _fake_git(stdout="")
    ensure_clean_generator_tree(run=run)
    ((args, kwargs),) = calls
    assert args == ["git", "status", "--porcelain", "--", "."]
    assert kwargs["cwd"] == TOOL_ROOT


@pytest.mark.parametrize("status", [" M generator/cli.py\n", "?? templates/new_layout.csv\n"])
def test_modified_or_untracked_files_refuse_and_name_them(status):
    run, _ = _fake_git(stdout=status)
    with pytest.raises(DirtyTreeError) as exc:
        ensure_clean_generator_tree(run=run)
    assert status.strip() in str(exc.value)


def test_unreadable_git_status_refuses():
    run, _ = _fake_git(error=subprocess.CalledProcessError(128, ["git"], stderr="not a git repository"))
    with pytest.raises(DirtyTreeError):
        ensure_clean_generator_tree(run=run)


def test_cli_generate_refuses_before_writing_anything(tmp_path, monkeypatch, capsys):
    def dirty():
        raise DirtyTreeError("uncommitted changes in tools/generate_invoices/:\n M generator/cli.py")

    def must_not_run(out_dir):
        raise AssertionError("generate_dataset ran on a dirty tree")

    monkeypatch.setattr(cli, "ensure_clean_generator_tree", dirty)
    monkeypatch.setattr(cli, "generate_dataset", must_not_run)

    assert cli.main(["generate", "--out-dir", str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []
    assert "Generation refused" in capsys.readouterr().err
