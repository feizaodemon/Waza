"""Regression tests for Health's default no-project-command contract."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "health" / "SKILL.md"
COLLECTOR = ROOT / "skills" / "health" / "scripts" / "collect-data.sh"


def run(command: list[str], cwd: Path):
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state(root: Path) -> tuple[str, str, str]:
    return (
        run(["git", "rev-parse", "HEAD"], root).stdout,
        run(["git", "status", "--porcelain"], root).stdout,
        run(["git", "diff", "--cached", "--name-only"], root).stdout,
    )


def make_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "example-repo"
    root.mkdir()
    (root / ".gitignore").write_text("ignored-fixture.txt\nmarker.txt\n")
    (root / "AGENTS.md").write_text(
        "# Agent guide\n\n"
        "Verifier: `python verify.py`.\n"
        "Other definitions: `npm test`, `make check`, and `python -m unittest`.\n"
    )
    (root / "README.md").write_text(
        "Project tests: `npm test`, `make check`, `python verify.py`, and "
        "`python -m unittest`.\n"
    )
    marker = root / "marker.txt"
    ignored = root / "ignored-fixture.txt"
    ignored.write_bytes(b"ignored fixture baseline\n")
    (root / "verify.py").write_text(
        "from pathlib import Path\n"
        "Path('marker.txt').write_text('executed')\n"
        "Path('ignored-fixture.txt').write_text('mutated')\n"
    )
    assert run(["git", "init", "-b", "main"], root).returncode == 0
    assert run(
        ["git", "add", ".gitignore", "AGENTS.md", "README.md", "verify.py"], root
    ).returncode == 0
    commit = run(
        [
            "git",
            "-c",
            "user.name=Health Test",
            "-c",
            "user.email=health-test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        root,
    )
    assert commit.returncode == 0, commit.stderr
    return root, ignored, marker


def collector_command(mode: str) -> list[str]:
    if os.name == "nt":
        pytest.skip("POSIX collector integration runs in upstream CI")
    return ["bash", str(COLLECTOR), "auto", mode]


@pytest.mark.parametrize("mode", ["summary", "deep"])
def test_collector_reports_commands_without_executing_them(tmp_path: Path, mode: str):
    root, ignored, marker = make_project(tmp_path)
    before_git = git_state(root)
    before_hash = sha256(ignored)

    result = run(collector_command(mode), root)

    assert result.returncode == 0, result.stderr
    for command in ("npm test", "make check", "verify.py", "python -m unittest"):
        assert command in result.stdout
    assert not marker.exists()
    assert sha256(ignored) == before_hash
    assert git_state(root) == before_git


def test_skill_contract_requires_explicit_live_verification():
    text = SKILL.read_text(encoding="utf-8")

    assert "Default summary/report-only" in text
    assert "Deep report-only" in text
    assert "Explicit live verification" in text
    assert "does not execute project test suites" in text
    assert "Neutral prompts do not authorize live verification" in text
    for detail in ("command", "expected writes", "target paths", "isolation strategy", "rollback"):
        assert detail in text
