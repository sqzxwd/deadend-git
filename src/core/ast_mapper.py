"""AST symbol mapper for extracting functions, classes, and methods from Python source code."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SymbolInfo:
    """Represents a code symbol (function, async function, method, or class)."""

    name: str
    short_name: str
    symbol_type: str  # "function", "async_function", "method", "async_method", "class"
    start_line: int
    end_line: int
    signature: str
    file_path: str = ""

    def contains_line(self, line_number: int) -> bool:
        """Check if line_number falls within the symbol's start and end line boundaries."""
        return self.start_line <= line_number <= self.end_line

    @property
    def span(self) -> int:
        """Span length in lines."""
        return max(0, self.end_line - self.start_line)

    def to_dict(self) -> dict[str, Any]:
        """Convert symbol info to dictionary."""
        return {
            "name": self.name,
            "short_name": self.short_name,
            "symbol_type": self.symbol_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
            "file_path": self.file_path,
        }


class _SymbolCollector(ast.NodeVisitor):
    """AST visitor that collects classes and functions with nesting context."""

    def __init__(self, file_path: str = "") -> None:
        self.file_path = file_path
        self.symbols: list[SymbolInfo] = []
        self._scope_stack: list[tuple[str, str]] = []  # (name, type)

    def _get_qualified_name(self, name: str) -> str:
        if not self._scope_stack:
            return name
        parent_names = [item[0] for item in self._scope_stack]
        return ".".join(parent_names + [name])

    def _is_inside_class(self) -> bool:
        return any(scope_type == "class" for _, scope_type in self._scope_stack)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        full_name = self._get_qualified_name(node.name)
        bases = [ast.unparse(b) for b in node.bases]
        keywords = [
            f"{kw.arg}={ast.unparse(kw.value)}" if kw.arg else f"**{ast.unparse(kw.value)}"
            for kw in node.keywords
        ]
        all_parts = bases + keywords
        sig = f"({', '.join(all_parts)})" if all_parts else "()"

        sym = SymbolInfo(
            name=full_name,
            short_name=node.name,
            symbol_type="class",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=sig,
            file_path=self.file_path,
        )
        self.symbols.append(sym)

        self._scope_stack.append((node.name, "class"))
        self.generic_visit(node)
        self._scope_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        full_name = self._get_qualified_name(node.name)
        in_class = self._is_inside_class()

        if in_class:
            sym_type = "async_method" if is_async else "method"
        else:
            sym_type = "async_function" if is_async else "function"

        args_str = ast.unparse(node.args)
        if node.returns:
            ret_str = ast.unparse(node.returns)
            sig = f"({args_str}) -> {ret_str}"
        else:
            sig = f"({args_str})"

        sym = SymbolInfo(
            name=full_name,
            short_name=node.name,
            symbol_type=sym_type,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=sig,
            file_path=self.file_path,
        )
        self.symbols.append(sym)

        self._scope_stack.append((node.name, sym_type))
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)


class SymbolMapper:
    """Parses Python files and maps code locations to functions, methods, and classes."""

    def __init__(
        self,
        file_path: str | Path | None = None,
        source_code: str | None = None,
    ) -> None:
        self.file_path = str(file_path) if file_path else ""
        self.source_code = source_code
        self.symbols: list[SymbolInfo] = []

        if file_path or source_code:
            self.parse(file_path=file_path, source_code=source_code)

    def parse(
        self,
        file_path: str | Path | None = None,
        source_code: str | None = None,
    ) -> list[SymbolInfo]:
        """Parse source code or file path and extract symbols."""
        if file_path:
            self.file_path = str(file_path)
        if source_code is not None:
            self.source_code = source_code
        elif self.file_path and Path(self.file_path).exists():
            self.source_code = Path(self.file_path).read_text(encoding="utf-8")

        if not self.source_code:
            self.symbols = []
            return self.symbols

        try:
            tree = ast.parse(self.source_code, filename=self.file_path or "<string>")
        except SyntaxError:
            self.symbols = []
            return self.symbols

        collector = _SymbolCollector(file_path=self.file_path)
        collector.visit(tree)
        self.symbols = collector.symbols
        return self.symbols

    def get_symbols(self) -> list[SymbolInfo]:
        """Return all parsed symbols."""
        return list(self.symbols)

    def find_by_line(self, line_number: int) -> SymbolInfo | None:
        """Find the innermost symbol that covers line_number."""
        matching = [s for s in self.symbols if s.contains_line(line_number)]
        if not matching:
            return None
        # Return innermost (smallest span)
        return min(matching, key=lambda s: s.span)

    def find_by_name(self, symbol_name: str) -> SymbolInfo | None:
        """Find symbol by fully qualified name or short name."""
        symbol_name = symbol_name.strip()
        # 1. Exact match on qualified name
        for s in self.symbols:
            if s.name == symbol_name:
                return s
        # 2. Exact match on short name
        for s in self.symbols:
            if s.short_name == symbol_name:
                return s
        # 3. Case-insensitive match
        symbol_name_lower = symbol_name.lower()
        for s in self.symbols:
            if s.name.lower() == symbol_name_lower or s.short_name.lower() == symbol_name_lower:
                return s
        return None

    def find_symbol(self, target: str | int) -> SymbolInfo | None:
        """Find symbol by line number (int or numeric string) or by name."""
        if isinstance(target, int):
            return self.find_by_line(target)
        if isinstance(target, str) and target.strip().isdigit():
            return self.find_by_line(int(target.strip()))
        return self.find_by_name(str(target))

    @classmethod
    def find_symbols_in_file(cls, file_path: str | Path) -> list[SymbolInfo]:
        """Convenience method to extract symbols from a file."""
        mapper = cls(file_path=file_path)
        return mapper.get_symbols()

    @classmethod
    def find_symbols_in_files(
        cls, file_paths: list[str | Path]
    ) -> dict[str, list[SymbolInfo]]:
        """Extract symbols from a list of files (e.g. modified files)."""
        result: dict[str, list[SymbolInfo]] = {}
        for path in file_paths:
            p = Path(path)
            if p.suffix == ".py" and p.is_file():
                symbols = cls.find_symbols_in_file(p)
                result[str(path)] = symbols
        return result
