"""
Aegis — Patch Validator

Validates candidate self-healing code patches against non-negotiable security,
scope, syntax, and quality thresholds before promotion.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Outcome of safety and quality validation for a proposed patch."""

    is_valid: bool
    checks_passed: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class PatchValidator:
    """Validator enforcing security and scope boundaries on code patches."""

    MAX_DIFF_LINES: int = 200

    FORBIDDEN_IMPORTS: set[str] = {
        "subprocess",
        "os.system",
        "pty",
        "ctypes",
        "socket",
        "builtins",
    }

    FORBIDDEN_CALLS: set[str] = {
        "eval",
        "exec",
        "__import__",
        "os.system",
        "os.popen",
        "subprocess.Popen",
        "subprocess.run",
        "subprocess.call",
    }

    SECRET_PATTERNS = [
        re.compile(r"api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE),
        re.compile(r"bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),
        re.compile(r"-----BEGIN\s+PRIVATE\s+KEY-----", re.IGNORECASE),
        re.compile(r"aws[_-]?secret[_-]?access[_-]?key", re.IGNORECASE),
    ]

    def validate_patch(
        self,
        target_file_rel: str,
        diff_content: str,
        patched_full_code: str,
    ) -> ValidationResult:
        """
        Enforce all safety gate checks on a proposed patch.
        """
        passed: list[str] = []
        failed: list[str] = []

        # 1. Target Scope Check: Must be in connectors/ directory
        if not (target_file_rel.startswith("connectors/") or "/connectors/" in target_file_rel):
            failed.append(f"Scope violation: patch target '{target_file_rel}' is not inside connectors/")
        else:
            passed.append("Target scope check (connectors/ subpath)")

        # 2. Diff Size Check: Max 200 lines
        diff_line_count = len(diff_content.splitlines())
        if diff_line_count > self.MAX_DIFF_LINES:
            failed.append(f"Diff size limit exceeded: {diff_line_count} lines (max {self.MAX_DIFF_LINES})")
        else:
            passed.append(f"Diff size check ({diff_line_count} <= {self.MAX_DIFF_LINES} lines)")

        # 3. Python AST Syntax Check
        try:
            tree = ast.parse(patched_full_code, filename=target_file_rel)
            passed.append("Python AST syntax check")
        except SyntaxError as syn_err:
            failed.append(f"Syntax error in patched code: {syn_err}")
            return ValidationResult(is_valid=False, checks_passed=passed, failures=failed)

        # 4. Forbidden Imports & Calls AST Inspection
        forbidden_found = self._check_forbidden_ast_nodes(tree)
        if forbidden_found:
            failed.extend([f"Forbidden code detected: {item}" for item in forbidden_found])
        else:
            passed.append("Forbidden imports and call checks")

        # 5. Secret Leak Check
        secrets_found = False
        for line in diff_content.splitlines():
            if line.startswith("+"):
                for pattern in self.SECRET_PATTERNS:
                    if pattern.search(line):
                        failed.append(f"Secret leakage detected in diff: '{line.strip()[:40]}...'")
                        secrets_found = True
                        break
        if not secrets_found:
            passed.append("Hardcoded secret leakage check")

        is_valid = len(failed) == 0
        return ValidationResult(
            is_valid=is_valid,
            checks_passed=passed,
            failures=failed,
            details={
                "diff_lines": diff_line_count,
                "target_file": target_file_rel,
            },
        )

    def _check_forbidden_ast_nodes(self, tree: ast.AST) -> list[str]:
        """Walk AST to find forbidden import statements or unsafe callables."""
        forbidden: list[str] = []

        for node in ast.walk(tree):
            # Check imports e.g. import subprocess
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_IMPORTS:
                        forbidden.append(f"import {alias.name}")
            # Check from imports e.g. from os import system
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    full_name = f"{module}.{alias.name}" if module else alias.name
                    if module in self.FORBIDDEN_IMPORTS or full_name in self.FORBIDDEN_IMPORTS:
                        forbidden.append(f"from {module} import {alias.name}")

            # Check function calls e.g. eval(), exec(), os.system()
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.FORBIDDEN_CALLS:
                        forbidden.append(f"call to {node.func.id}()")
                elif isinstance(node.func, ast.Attribute):
                    val_id = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                    attr_call = f"{val_id}.{node.func.attr}"
                    if attr_call in self.FORBIDDEN_CALLS:
                        forbidden.append(f"call to {attr_call}()")

        return forbidden
