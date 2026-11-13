"""Command-line interface for deadend-git powered by Typer and Rich."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.ast_mapper import SymbolMapper
from src.core.git_ledger import DeadEndLedger, GitLedgerError
from src.server import server

app = typer.Typer(
    name="deadend",
    help="Collective error memory & dead-end ledger for git repositories.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def record(
    file: Annotated[
        str,
        typer.Option("--file", "-f", help="Target Python file path", prompt=True),
    ],
    symbol: Annotated[
        str,
        typer.Option("--symbol", "-s", help="Target function, method, or class name", prompt=True),
    ],
    approach: Annotated[
        str,
        typer.Option("--approach", "-a", help="Description of the attempted approach", prompt=True),
    ],
    reason: Annotated[
        str,
        typer.Option("--reason", "-r", help="Why the approach failed or broke tests", prompt=True),
    ],
    tags: Annotated[
        Optional[list[str]],
        typer.Option("--tag", "-t", help="Optional tags for indexing (repeatable)"),
    ] = None,
) -> None:
    """Record a failed technical approach into git notes (refs/notes/deadends)."""
    try:
        ledger = DeadEndLedger()
        rec = ledger.record_deadend(
            file_path=file,
            symbol_name=symbol,
            approach=approach,
            reason=reason,
            tags=tags or [],
        )

        commit_short = rec.get("commit", "HEAD")[:7]
        content = (
            f"[bold]ID:[/bold] [cyan]{rec['id']}[/cyan]\n"
            f"[bold]Target:[/bold] [yellow]{rec['file_path']}::{rec['symbol_name']}[/yellow]\n"
            f"[bold]Approach:[/bold] {rec['approach']}\n"
            f"[bold]Reason:[/bold] [red]{rec['reason']}[/red]\n"
            f"[bold]Commit:[/bold] {commit_short}\n"
            f"[bold]Stored at:[/bold] refs/notes/deadends"
        )
        if rec.get("tags"):
            content += f"\n[bold]Tags:[/bold] {', '.join(rec['tags'])}"

        console.print(
            Panel(
                content,
                title="[bold green]✔ Dead-End Successfully Recorded[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )
    except GitLedgerError as e:
        console.print(f"[bold red]Git Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def check(
    file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="Specific file to check (defaults to modified files)"),
    ] = None,
    symbol: Annotated[
        Optional[str],
        typer.Option("--symbol", "-s", help="Specific symbol name to check"),
    ] = None,
) -> None:
    """Check working files or a specific file/symbol for past dead ends and warnings."""
    try:
        ledger = DeadEndLedger()
    except Exception as e:
        console.print(f"[bold red]Failed to access git repository:[/bold red] {e}")
        raise typer.Exit(code=1)

    matching_records: list[dict] = []

    if file:
        files_to_check = [file]
    else:
        files_to_check = ledger.get_modified_files()
        if not files_to_check:
            console.print("[green]✔ No modified files in git status. Workspace is clean.[/green]")
            return

    # Scan records for target files and their AST symbols
    for f in files_to_check:
        # 1. Direct search by file and symbol
        records = ledger.find_deadends(file_path=f, symbol_name=symbol)
        for r in records:
            if r not in matching_records:
                matching_records.append(r)

        # 2. If no symbol was given, inspect symbols in Python file
        if not symbol and Path(f).is_file() and f.endswith(".py"):
            symbols = SymbolMapper.find_symbols_in_file(f)
            for sym in symbols:
                sym_records = ledger.find_deadends(file_path=f, symbol_name=sym.name)
                for r in sym_records:
                    if r not in matching_records:
                        matching_records.append(r)

    if not matching_records:
        console.print(
            Panel(
                f"[green]✔ No dead ends found for checked targets: {', '.join(files_to_check)}.\n"
                f"Safe to proceed with coding![/green]",
                title="[bold green]Dead-End Audit: PASS[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )
        return

    # Render warning table
    table = Table(
        title="⚠️  [bold red]DEAD-END WARNING: Previously Failed Approaches Detected[/bold red]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Symbol / Location", style="yellow", overflow="fold")
    table.add_column("Attempted Approach", style="white", overflow="fold")
    table.add_column("Why It Failed (Reason)", style="red", overflow="fold")
    table.add_column("Commit / Date", style="dim cyan", overflow="fold")

    for rec in matching_records:
        commit_short = rec.get("commit", "unknown")[:7]
        date_str = rec.get("timestamp", "")[:10]
        location = f"{rec.get('file_path')}::{rec.get('symbol_name')}"
        table.add_row(
            location,
            rec.get("approach", ""),
            rec.get("reason", ""),
            f"{commit_short}\n{date_str}",
        )

    console.print(table)
    console.print(
        "[bold red]⛔ Stop! Review the table above before writing code to avoid repeating these mistakes.[/bold red]"
    )


@app.command(name="list")
def list_deadends(
    file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="Filter by file path"),
    ] = None,
    symbol: Annotated[
        Optional[str],
        typer.Option("--symbol", "-s", help="Filter by symbol name"),
    ] = None,
) -> None:
    """Show the graveyard of all dead-end technical approaches recorded in the repo."""
    try:
        ledger = DeadEndLedger()
        records = ledger.find_deadends(file_path=file, symbol_name=symbol)
    except Exception as e:
        console.print(f"[bold red]Error querying ledger:[/bold red] {e}")
        raise typer.Exit(code=1)

    if not records:
        console.print("[dim]The repository dead-end ledger is empty. No failures recorded yet.[/dim]")
        return

    table = Table(
        title=f"🪦 [bold cyan]Dead-End Ledger ({len(records)} entries)[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("ID", style="dim", width=10)
    table.add_column("Location", style="yellow", overflow="fold")
    table.add_column("Approach", style="white", overflow="fold")
    table.add_column("Failure Reason", style="red", overflow="fold")
    table.add_column("Commit", style="cyan", width=9)
    table.add_column("Tags", style="green", overflow="fold")

    for rec in records:
        loc = f"{rec.get('file_path')}::{rec.get('symbol_name')}"
        tags_str = ", ".join(rec.get("tags", [])) if rec.get("tags") else "-"
        table.add_row(
            rec.get("id", ""),
            loc,
            rec.get("approach", ""),
            rec.get("reason", ""),
            rec.get("commit", "")[:7],
            tags_str,
        )

    console.print(table)


@app.command()
def sync(
    remote: Annotated[
        str,
        typer.Option("--remote", help="Git remote name to sync notes with"),
    ] = "origin",
) -> None:
    """Sync refs/notes/deadends with the remote git repository."""
    ledger = DeadEndLedger()
    console.print(f"[cyan]Syncing dead-end notes with remote '{remote}'...[/cyan]")
    success, message = ledger.sync_notes(remote=remote)
    if success:
        console.print(Panel(message, title="[bold green]Sync Succeeded[/bold green]", border_style="green"))
    else:
        console.print(Panel(message, title="[bold red]Sync Failed[/bold red]", border_style="red"))
        raise typer.Exit(code=1)


@app.command()
def serve() -> None:
    """Start the FastMCP stdio server for AI coding agents."""
    console.print("[bold green]Starting deadend-git FastMCP server (stdio)...[/bold green]")
    server.run(transport="stdio")


if __name__ == "__main__":
    app()
