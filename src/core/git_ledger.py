"""Git ledger for managing dead-end notes via git notes --ref=deadends."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import uuid
from typing import Any


class GitLedgerError(Exception):
    """Custom exception for Git ledger operations."""


class DeadEndLedger:
    """Manages dead-end notes in git using refs/notes/deadends."""

    def __init__(self, repo_path: str | Path | None = None) -> None:
        self.repo_path = self._resolve_repo_path(repo_path)
        self.ref = "deadends"

    def _resolve_repo_path(self, repo_path: str | Path | None) -> Path:
        """Resolve repository root path."""
        target_path = Path(repo_path).resolve() if repo_path else Path.cwd()
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=target_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(res.stdout.strip()).resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return target_path

    def _run_git(
        self,
        *args: str,
        input_data: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a git command within the repository root."""
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                input=input_data,
                check=check,
            )
        except subprocess.CalledProcessError as e:
            cmd = " ".join(["git", *args])
            raise GitLedgerError(
                f"Command '{cmd}' failed (exit code {e.returncode}): {e.stderr.strip()}"
            ) from e

    def get_head_commit(self) -> str:
        """Get the current commit hash (HEAD)."""
        res = self._run_git("rev-parse", "HEAD")
        return res.stdout.strip()

    def _normalize_file_path(self, file_path: str | Path) -> str:
        """Normalize file path relative to repo root if possible, in POSIX format."""
        p = Path(file_path)
        if p.is_absolute():
            try:
                rel = p.relative_to(self.repo_path)
                return rel.as_posix()
            except ValueError:
                return p.as_posix()
        return p.as_posix()

    def _get_notes_for_commit(self, commit_sha: str) -> list[dict[str, Any]]:
        """Retrieve existing dead-end notes for a given commit."""
        try:
            res = self._run_git("notes", f"--ref={self.ref}", "show", commit_sha, check=True)
            raw = res.stdout.strip()
            if not raw:
                return []
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return []
        except (GitLedgerError, json.JSONDecodeError):
            return []

    def record_deadend(
        self,
        file_path: str,
        symbol_name: str,
        approach: str,
        reason: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record a dead-end technical attempt in git notes for the current HEAD commit."""
        head_commit = self.get_head_commit()
        norm_file = self._normalize_file_path(file_path)

        existing_notes = self._get_notes_for_commit(head_commit)

        record = {
            "id": uuid.uuid4().hex[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_path": norm_file,
            "symbol_name": symbol_name.strip(),
            "approach": approach.strip(),
            "reason": reason.strip(),
            "tags": tags or [],
            "commit": head_commit,
        }

        existing_notes.append(record)
        json_content = json.dumps(existing_notes, indent=2, ensure_ascii=False)

        # Store note using stdin to safely handle multiline and special characters
        self._run_git(
            "notes",
            f"--ref={self.ref}",
            "add",
            "-f",
            "-F",
            "-",
            head_commit,
            input_data=json_content,
        )

        return record

    def find_deadends(
        self,
        file_path: str | None = None,
        symbol_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Scan all notes in refs/notes/deadends and return matching records."""
        try:
            res = self._run_git("notes", f"--ref={self.ref}", "list", check=True)
        except GitLedgerError:
            return []

        raw_list = res.stdout.strip().splitlines()
        all_records: list[dict[str, Any]] = []

        target_file = self._normalize_file_path(file_path) if file_path else None
        target_symbol = symbol_name.strip() if symbol_name else None

        for line in raw_list:
            parts = line.split()
            if len(parts) < 2:
                continue
            blob_sha, commit_sha = parts[0], parts[1]

            # Read note contents directly from blob
            try:
                blob_res = self._run_git("cat-file", "-p", blob_sha, check=True)
                raw_json = blob_res.stdout.strip()
                if not raw_json:
                    continue
                data = json.loads(raw_json)
                entries = data if isinstance(data, list) else [data]
            except (GitLedgerError, json.JSONDecodeError):
                continue

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if "commit" not in entry:
                    entry["commit"] = commit_sha

                # Check file filter
                if target_file:
                    rec_file = entry.get("file_path", "")
                    # Match exact or suffix (for relative / absolute variations)
                    if (
                        rec_file != target_file
                        and not rec_file.endswith(f"/{target_file}")
                        and not target_file.endswith(f"/{rec_file}")
                    ):
                        continue

                # Check symbol filter
                if target_symbol:
                    rec_sym = entry.get("symbol_name", "")
                    if (
                        rec_sym != target_symbol
                        and not rec_sym.endswith(f".{target_symbol}")
                        and not target_symbol.endswith(f".{rec_sym}")
                    ):
                        continue

                all_records.append(entry)

        # Sort descending by timestamp
        all_records.sort(
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )
        return all_records

    def get_modified_files(self) -> list[str]:
        """Get list of modified/untracked files from git status --porcelain."""
        try:
            res = self._run_git("status", "--porcelain", check=True)
        except GitLedgerError:
            return []

        modified_files: list[str] = []
        for line in res.stdout.splitlines():
            if not line or len(line) < 4:
                continue
            # Format: 'XY path' or 'XY orig -> new'
            file_part = line[3:].strip()
            if " -> " in file_part:
                file_part = file_part.split(" -> ")[-1].strip()

            # Remove quotes if git formatted the path with quotes
            if file_part.startswith('"') and file_part.endswith('"'):
                file_part = file_part[1:-1]

            norm = self._normalize_file_path(file_part)
            if norm not in modified_files:
                modified_files.append(norm)

        return modified_files

    def sync_notes(self, remote: str = "origin") -> tuple[bool, str]:
        """Sync refs/notes/deadends with remote repository (fetch and push)."""
        messages: list[str] = []
        refspec = f"refs/notes/{self.ref}:refs/notes/{self.ref}"

        # 1. Fetch remote notes
        try:
            fetch_res = self._run_git("fetch", remote, refspec, check=True)
            msg = fetch_res.stderr.strip() or fetch_res.stdout.strip()
            messages.append(f"Fetched notes: {msg}" if msg else "Fetched notes successfully.")
        except GitLedgerError as e:
            messages.append(f"Fetch notes warning/info: {e}")

        # 2. Push local notes
        try:
            push_res = self._run_git("push", remote, refspec, check=True)
            msg = push_res.stderr.strip() or push_res.stdout.strip()
            messages.append(f"Pushed notes: {msg}" if msg else "Pushed notes successfully.")
            return True, "\n".join(messages)
        except GitLedgerError as e:
            messages.append(f"Push notes failed: {e}")
            return False, "\n".join(messages)
