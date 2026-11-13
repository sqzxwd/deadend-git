"""FastMCP server providing dead-end ledger tools for AI coding agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]

from src.core.ast_mapper import SymbolMapper
from src.core.git_ledger import DeadEndLedger, GitLedgerError

server = FastMCP(
    name="deadend-git",
    instructions="Protocol of collective error memory and dead-end ledger for multi-agent development.",
)


def _format_warning(records: list[dict[str, Any]], target_file: str, target_symbol: str = "") -> str:
    """Format matching dead-end records into a structured agent alert."""
    target_str = f"{target_file}::{target_symbol}" if target_symbol else target_file
    lines = [
        f"⚠️  [DEAD-END ALERT] Found {len(records)} failed attempt(s) for '{target_str}':",
        "",
    ]
    for idx, rec in enumerate(records, 1):
        commit_short = rec.get("commit", "unknown")[:7]
        lines.append(f"{idx}. Target: {rec.get('file_path', '')}::{rec.get('symbol_name', '')}")
        lines.append(f"   Approach: {rec.get('approach', '')}")
        lines.append(f"   Failure Reason: {rec.get('reason', '')}")
        lines.append(f"   Recorded: {rec.get('timestamp', '')} (commit: {commit_short})")
        if rec.get("tags"):
            lines.append(f"   Tags: {', '.join(rec['tags'])}")
        lines.append("")
    lines.append("⛔ DO NOT repeat these failed approaches. Design an alternative architecture.")
    return "\n".join(lines)


@server.tool()
def check_deadends(file_path: str, symbol_name: str = "") -> str:
    """Check if there are any previously recorded dead ends or failed refactoring attempts

    for this file or function. Always call this tool before modifying a function.
    """
    try:
        ledger = DeadEndLedger()
    except Exception as e:
        return f"Error initializing git ledger: {e}"

    # Search for specific file and symbol
    direct_records = ledger.find_deadends(
        file_path=file_path,
        symbol_name=symbol_name if symbol_name else None,
    )

    if direct_records:
        return _format_warning(direct_records, file_path, symbol_name)

    # If symbol_name is not provided, also check known symbols inside file
    if not symbol_name and Path(file_path).is_file():
        file_symbols = SymbolMapper.find_symbols_in_file(file_path)
        all_file_deadends: list[dict[str, Any]] = []
        for sym in file_symbols:
            matched = ledger.find_deadends(file_path=file_path, symbol_name=sym.name)
            for m in matched:
                if m not in all_file_deadends:
                    all_file_deadends.append(m)
        if all_file_deadends:
            return _format_warning(all_file_deadends, file_path, "")

    target_str = f"{file_path}::{symbol_name}" if symbol_name else file_path
    return f"✅ No dead ends recorded for '{target_str}'. Safe to proceed with implementation."


@server.tool()
def record_deadend(file_path: str, symbol_name: str, approach: str, reason: str) -> str:
    """Record a failed technical approach and the error/reason it broke.

    Use this tool whenever tests fail or an implementation approach proves to be a dead end.
    """
    try:
        ledger = DeadEndLedger()
        rec = ledger.record_deadend(
            file_path=file_path,
            symbol_name=symbol_name,
            approach=approach,
            reason=reason,
        )
        commit_short = rec.get("commit", "unknown")[:7]
        return (
            f"📝 Successfully recorded dead end [{rec['id']}] for {file_path}::{symbol_name}.\n"
            f"Approach: '{approach}'\n"
            f"Reason: '{reason}'\n"
            f"Stored in git notes (refs/notes/deadends) at commit {commit_short}."
        )
    except GitLedgerError as e:
        return f"Failed to record dead end in git notes: {e}"
    except Exception as e:
        return f"Unexpected error while recording dead end: {e}"


@server.tool()
def list_all_deadends() -> str:
    """List all recorded dead-end technical approaches in the entire repository."""
    try:
        ledger = DeadEndLedger()
        records = ledger.find_deadends()
        if not records:
            return "🪦 Repository dead-end ledger is currently empty. No dead ends recorded."

        lines = [
            f"🪦 Repository Dead-End Ledger ({len(records)} total recorded failures):",
            "=" * 70,
        ]
        for idx, rec in enumerate(records, 1):
            commit_short = rec.get("commit", "unknown")[:7]
            lines.append(f"[{rec.get('id', 'N/A')}] {rec.get('file_path')} :: {rec.get('symbol_name')}")
            lines.append(f"  • Attempted: {rec.get('approach')}")
            lines.append(f"  • Failed because: {rec.get('reason')}")
            lines.append(f"  • Commit: {commit_short} on {rec.get('timestamp')}")
            if rec.get("tags"):
                lines.append(f"  • Tags: {', '.join(rec['tags'])}")
            lines.append("-" * 70)
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing dead ends: {e}"
