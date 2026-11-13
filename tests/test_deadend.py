"""Test suite for deadend-git (AST mapper, Git ledger, CLI, and FastMCP server)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import anyio
import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.ast_mapper import SymbolMapper
from src.core.git_ledger import DeadEndLedger
from src.server import check_deadends, list_all_deadends, record_deadend, server


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Initialize a git repository in a temporary directory."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Configure git
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "DeadEnd Tester"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@deadend.dev"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Initial commit
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


def test_ast_symbol_mapper(tmp_path: Path) -> None:
    """Test AST symbol extraction, line lookup, and method qualifying."""
    py_file = tmp_path / "service.py"
    py_file.write_text(
        '''"""Module docstring."""

class TaxEngine:
    def __init__(self, default_rate: float = 0.2):
        self.rate = default_rate

    async def calculate_tax(self, amount: float) -> float:
        """Calculate tax asynchronously."""
        return amount * self.rate

def calculate_flat_tax(price: float) -> float:
    return price * 0.15
''',
        encoding="utf-8",
    )

    mapper = SymbolMapper(file_path=py_file)
    symbols = mapper.get_symbols()

    # Verify classes and methods extracted
    names = [s.name for s in symbols]
    assert "TaxEngine" in names
    assert "TaxEngine.__init__" in names
    assert "TaxEngine.calculate_tax" in names
    assert "calculate_flat_tax" in names

    # Verify types and signatures
    async_tax = mapper.find_by_name("TaxEngine.calculate_tax")
    assert async_tax is not None
    assert async_tax.symbol_type == "async_method"
    assert "amount: float" in async_tax.signature

    # Lookup by short name
    short_match = mapper.find_by_name("calculate_tax")
    assert short_match is not None
    assert short_match.name == "TaxEngine.calculate_tax"

    # Line number lookup
    sym_at_line = mapper.find_by_line(8)
    assert sym_at_line is not None
    assert sym_at_line.short_name == "calculate_tax"

    # Files mapper
    file_map = SymbolMapper.find_symbols_in_files([py_file])
    assert str(py_file) in file_map
    assert len(file_map[str(py_file)]) == 4


def test_ledger_record_and_find_across_commits(git_repo: Path) -> None:
    """Test recording a dead end and finding it after subsequent commits and line shifting."""
    ledger = DeadEndLedger(repo_path=git_repo)

    # 1. Create python file with calculate_tax
    tax_file = git_repo / "tax_calculator.py"
    tax_file.write_text(
        """def calculate_tax(amount: float) -> float:
    # First naive implementation
    return amount * 0.2
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "tax_calculator.py"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add tax calculator"],
        cwd=git_repo,
        check=True,
    )

    # 2. Record dead end for calculate_tax
    record = ledger.record_deadend(
        file_path="tax_calculator.py",
        symbol_name="calculate_tax",
        approach="Static 20% multiplier",
        reason="Does not comply with progressive state tax regulations",
        tags=["taxes", "compliance"],
    )
    assert record["symbol_name"] == "calculate_tax"
    assert record["id"]

    # 3. Create new commits and shift lines in tax_calculator.py
    for i in range(1, 3):
        tax_file.write_text(
            f"""# Shift lines by inserting comments and helper functions (Commit {i})
def helper_one():
    return 1

def helper_two():
    return 2

def calculate_tax(amount: float) -> float:
    # Modified implementation in commit {i}
    return amount * 0.25
""",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "tax_calculator.py"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Refactor tax calculator iteration {i}"],
            cwd=git_repo,
            check=True,
        )

    # 4. Verify find_deadends still finds the dead end by function name and file
    results = ledger.find_deadends(file_path="tax_calculator.py", symbol_name="calculate_tax")
    assert len(results) == 1
    found = results[0]
    assert found["symbol_name"] == "calculate_tax"
    assert found["approach"] == "Static 20% multiplier"
    assert "progressive state tax regulations" in found["reason"]
    assert "compliance" in found["tags"]

    # Test filtering by file only
    file_results = ledger.find_deadends(file_path="tax_calculator.py")
    assert len(file_results) >= 1

    # Test filtering with non-matching symbol
    empty_results = ledger.find_deadends(
        file_path="tax_calculator.py", symbol_name="non_existent"
    )
    assert len(empty_results) == 0


def test_cli_commands(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI commands: record, check, list, and git status integration."""
    monkeypatch.chdir(git_repo)
    runner = CliRunner(env={"COLUMNS": "160"})

    # Create test file
    code_file = git_repo / "billing.py"
    code_file.write_text(
        """def process_payment(card_id: str, amount: float):
    return True
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "billing.py"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Add billing"], cwd=git_repo, check=True)

    # 1. Test CLI 'record'
    record_res = runner.invoke(
        app,
        [
            "record",
            "--file",
            "billing.py",
            "--symbol",
            "process_payment",
            "--approach",
            "Synchronous HTTP call to legacy gateway",
            "--reason",
            "Gateway times out on peak loads causing unhandled exceptions",
            "--tag",
            "billing",
            "--tag",
            "latency",
        ],
    )
    assert record_res.exit_code == 0
    assert "Dead-End Successfully Recorded" in record_res.stdout

    # 2. Test CLI 'list'
    list_res = runner.invoke(app, ["list"])
    assert list_res.exit_code == 0
    assert "Dead-End Ledger" in list_res.stdout
    assert "billing.py::process_payment" in list_res.stdout
    assert "Synchronous HTTP call" in list_res.stdout

    # 3. Test CLI 'check' for specific file
    check_file_res = runner.invoke(app, ["check", "--file", "billing.py"])
    assert check_file_res.exit_code == 0
    assert "DEAD-END WARNING" in check_file_res.stdout
    assert "billing.py::process_payment" in check_file_res.stdout

    # 4. Test CLI 'check' on modified files in git status
    code_file.write_text(
        """def process_payment(card_id: str, amount: float):
    # Modifying in working directory
    return False
""",
        encoding="utf-8",
    )
    check_modified_res = runner.invoke(app, ["check"])
    assert check_modified_res.exit_code == 0
    assert "DEAD-END WARNING" in check_modified_res.stdout
    assert "billing.py::process_payment" in check_modified_res.stdout

    # 5. Test CLI 'check' on clean file with no dead ends
    clean_file = git_repo / "clean.py"
    clean_file.write_text("def ok_func(): pass\n", encoding="utf-8")
    check_clean_res = runner.invoke(app, ["check", "--file", "clean.py"])
    assert check_clean_res.exit_code == 0
    assert "No dead ends found" in check_clean_res.stdout


def test_sync_notes(git_repo: Path, tmp_path: Path) -> None:
    """Test synchronizing dead-end notes with a remote git repository."""
    # Setup a local bare remote
    bare_remote = tmp_path / "bare_remote.git"
    subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)

    # Add origin to git_repo
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare_remote)],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    # Push initial main branch
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=git_repo, check=True, capture_output=True)

    ledger = DeadEndLedger(repo_path=git_repo)
    ledger.record_deadend(
        file_path="sync_test.py",
        symbol_name="sync_func",
        approach="Local approach",
        reason="Needs sync",
    )

    success, message = ledger.sync_notes(remote="origin")
    assert success is True
    assert "Pushed notes successfully" in message or "pushed" in message.lower()

    # Verify a second cloned repo can fetch the notes
    clone_dir = tmp_path / "clone_repo"
    subprocess.run(["git", "clone", str(bare_remote), str(clone_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "fetch", "origin", "refs/notes/deadends:refs/notes/deadends"],
        cwd=clone_dir,
        check=True,
        capture_output=True,
    )

    clone_ledger = DeadEndLedger(repo_path=clone_dir)
    cloned_deadends = clone_ledger.find_deadends(file_path="sync_test.py")
    assert len(cloned_deadends) == 1
    assert cloned_deadends[0]["symbol_name"] == "sync_func"


@pytest.mark.anyio
async def test_mcp_tools(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test FastMCP server tools check_deadends and record_deadend via anyio."""
    monkeypatch.chdir(git_repo)

    # 1. Initially check clean file
    clean_check = check_deadends("auth.py", "authenticate_user")
    assert "No dead ends recorded" in clean_check

    # 2. Record dead end using server tool
    rec_result = record_deadend(
        file_path="auth.py",
        symbol_name="authenticate_user",
        approach="Plain MD5 password hashing with salt",
        reason="Violates security standard; vulnerable to GPU rainbow attacks",
    )
    assert "Successfully recorded dead end" in rec_result
    assert "auth.py::authenticate_user" in rec_result

    # 3. Verify check_deadends now returns strong alert
    alert = check_deadends("auth.py", "authenticate_user")
    assert "DEAD-END ALERT" in alert
    assert "Plain MD5 password hashing" in alert
    assert "DO NOT repeat these failed approaches" in alert

    # 4. Verify list_all_deadends
    all_summary = list_all_deadends()
    assert "auth.py :: authenticate_user" in all_summary
    assert "rainbow attacks" in all_summary

    # 5. Verify call_tool directly via MCPServer instance
    res = await server.call_tool(
        "check_deadends",
        {"file_path": "auth.py", "symbol_name": "authenticate_user"},
    )
    assert not res.is_error
    assert len(res.content) > 0
    assert "DEAD-END ALERT" in res.content[0].text
