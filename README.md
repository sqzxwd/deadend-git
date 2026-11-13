# 🪦 deadend-git: Semantic Git Blame & Dead-End Ledger for AI Agents

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Git Notes](https://img.shields.io/badge/storage-git%20notes-orange.svg)](https://git-scm.com/docs/git-notes)
[![AST-Aware](https://img.shields.io/badge/symbol--mapping-python%20ast-brightgreen.svg)](#how-it-works)
[![Protocol](https://img.shields.io/badge/protocol-FastMCP%20%2F%20MCP%202.x-purple.svg)](https://modelcontextprotocol.io/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#quickstart)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**deadend-git** is an open-source collective error memory protocol and semantic dead-end ledger designed for multi-agent software engineering. It retains the institutional knowledge of failed technical approaches, broken refactoring attempts, and negative results without cluttering your commit history.

---

## 💥 The Problem

Standard Git only preserves **survivor bias**:
- When an engineer or AI agent attempts a refactoring that breaks edge cases or tanks performance, the changes are discarded (`git restore .` or `git reset --hard`).
- Commit history only documents **what worked**, erasing all evidence of **what failed and why**.
- Autonomous AI agents (Claude Code, Cursor, Antigravity, etc.) frequently repeat the exact same broken approaches, circular refactoring loops, and deprecated library experiments that previous agents or human developers already abandoned hours or weeks ago.

---

## 💡 The Solution

**deadend-git** turns Git into a semantic graveyard of failed attempts:
1. **Hidden Git Metadata (`refs/notes/deadends`)**: Stores structured failure logs in isolated Git notes attached to commit hashes. It never pollutes your branch history or pull requests.
2. **Python AST Symbol Binding**: Automatically maps line ranges to specific functions, methods, and classes using standard Python AST parsing. Even when code shifts 100 lines down in future commits, the failure note remains anchored to the logical symbol.
3. **Multi-Agent Pre-Flight Alerts**: Agents query the embedded FastMCP server before editing code to verify if an approach was previously proven defective.
4. **Developer CLI with Rich Visuals**: Rich tables and warning banners alert humans during pre-commit checks and code review.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.14+
- Standard Git CLI

### Installation

#### macOS / Linux
```bash
# Clone the repository
git clone https://github.com/your-org/deadend-git.git
cd deadend-git

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install package in editable mode
pip install -e .
```

#### Windows (PowerShell)
```powershell
# Clone the repository
git clone https://github.com/your-org/deadend-git.git
cd deadend-git

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install package in editable mode
pip install -e .
```

---

## 🤖 AI Agent Integration (MCP Configuration)

`deadend-git` exposes a Model Context Protocol (FastMCP) server via standard I/O (`stdio`). AI agents can check past failures before refactoring and automatically record dead ends when test runs fail.

Add the following to your agent's MCP configuration file:

### Configuration (`mcpServers`)
*For Google Antigravity, Claude Code (`claude_desktop_config.json`), or Cursor (`mcp.json`):*

```json
{
  "mcpServers": {
    "deadend-git": {
      "command": "deadend",
      "args": ["serve"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

> **Tip:** If running within a dedicated virtualenv, specify the full path to the executable (e.g. `/path/to/deadend-git/.venv/bin/deadend` on Unix or `C:\\path\\to\\deadend-git\\.venv\\Scripts\\deadend.exe` on Windows).

### Available MCP Tools for Agents
| Tool | Description |
|---|---|
| `check_deadends(file_path, symbol_name)` | Checks if past failed refactorings exist for the specified file or symbol before writing code. |
| `record_deadend(file_path, symbol_name, approach, reason)` | Commits a failed implementation attempt to repository memory when tests break. |
| `list_all_deadends()` | Returns a comprehensive summary of all historical dead ends in the project. |

---

## 💻 CLI Usage

```bash
# Display help and available commands
deadend --help
```

### 1. Record a Dead End
Record a failed experiment into `refs/notes/deadends` for the current `HEAD`:
```bash
deadend record \
  --file src/services/billing.py \
  --symbol process_payment \
  --approach "Synchronous HTTP call to legacy payment gateway" \
  --reason "Gateway times out under peak concurrency (>150 RPS), dropping transactions" \
  --tag billing --tag timeout
```

### 2. Check for Traps Before Coding
Audit modified files from `git status` (or specify a target file/symbol) to prevent repeating mistakes:
```bash
# Check all currently modified files in your working directory
deadend check

# Or check a specific file and function
deadend check --file src/services/billing.py --symbol process_payment
```

If past failures match, `deadend` displays an urgent terminal alert:
```
⚠️  DEAD-END WARNING: Previously Failed Approaches Detected
╭───────────────────────────────┬─────────────────────────────┬───────────────────────────┬──────────────╮
│ Symbol / Location             │ Attempted Approach          │ Why It Failed (Reason)    │ Commit / Date│
├───────────────────────────────┼─────────────────────────────┼───────────────────────────┼──────────────┤
│ billing.py::process_payment   │ Synchronous HTTP call to... │ Gateway times out unde... │ c02fc65      │
│                               │                             │                           │ 2026-11-13   │
╰───────────────────────────────┴─────────────────────────────┴───────────────────────────┴──────────────╯
⛔ Stop! Review the table above before writing code to avoid repeating these mistakes.
```

### 3. Browse the Failure Graveyard
List all recorded technical dead ends across the entire repository:
```bash
deadend list
```

### 4. Sync Dead-End Notes with Remote
Because Git notes are not pushed by standard `git push`, use `sync` to share failure memory with your team and CI/CD agents:
```bash
deadend sync --remote origin
```

### 5. Start FastMCP Server
Run the stdio MCP server for agent clients:
```bash
deadend serve
```

---

## 🛠️ How It Works

```
┌────────────────────────────────────────────────────────┐
│                      Developer / AI Agent              │
└───────────┬───────────────────────────────────┬────────┘
            │ 1. Pre-flight check               │ 2. Record dead end
            ▼                                   ▼
┌──────────────────────┐             ┌──────────────────────┐
│  AST Symbol Mapper   │             │   DeadEnd Ledger     │
│  (ast.NodeVisitor)   │             │  (git notes engine)  │
└───────────┬──────────┘             └──────────┬───────────┘
            │                                   │
            ▼                                   ▼
   Matches line ranges to           Saves structured JSON to
   classes, async & sync methods    refs/notes/deadends (HEAD)
```

1. **Symbol Mapping**: `src/core/ast_mapper.py` inspects Python source files using standard library `ast`. It resolves qualified symbol paths (`Class.method`), argument signatures, and line boundaries.
2. **Git Ledger**: `src/core/git_ledger.py` writes JSON objects into `refs/notes/deadends` using `git notes add -f -F -`. Because notes are keyed to commits, history remains intact even across branch checkouts.
3. **Resilience to Code Drift**: Line numbers change as files evolve. `deadend-git` binds notes to qualified symbol names and relative paths, guaranteeing warnings continue to fire even when a function moves hundreds of lines down.

---

## 🧪 Testing

The test suite runs with `pytest` and `anyio` on Python 3.14+:

```bash
pytest -v
```

All 5 core test suites run against an ephemeral git repository (`tmp_path`) validating AST mapping, note preservation across commits and line shifts, CLI operations, remote sync, and FastMCP tool execution.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
