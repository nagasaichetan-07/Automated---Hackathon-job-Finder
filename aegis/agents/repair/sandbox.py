"""
Aegis — Repair Sandbox

Provides an isolated environment (Git worktree or sandbox directory) to safely apply,
test, and validate proposed connector patches without modifying the working branch.
"""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SandboxResult:
    """Outcome of running tests inside the isolated sandbox."""

    success: bool
    exit_code: int
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    stdout: str = ""
    stderr: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class RepairSandbox:
    """Manages isolated patch execution and testing."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or os.getcwd()).resolve()

    def create_sandbox_env(self) -> Path:
        """Create a temporary sandbox copy of the project repository."""
        temp_dir = Path(tempfile.mkdtemp(prefix="aegis_sandbox_"))
        return temp_dir

    def apply_patch_to_file(self, target_file_path: Path, patch_diff: str) -> str:
        """
        Apply a unified diff string to a target file.
        Returns the modified file text content.
        """
        if not target_file_path.exists():
            raise FileNotFoundError(f"Target file for patch does not exist: {target_file_path}")

        original_lines = target_file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        patched_lines = self._apply_unified_diff(original_lines, patch_diff)
        patched_content = "".join(patched_lines)
        target_file_path.write_text(patched_content, encoding="utf-8")
        return patched_content

    def _apply_unified_diff(self, original_lines: list[str], diff_text: str) -> list[str]:
        """Parse and apply a unified diff to a list of original lines."""
        diff_lines = diff_text.splitlines(keepends=True)
        patched: list[str] = []
        orig_idx = 0

        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("@@"):
                # Parse hunk header e.g. @@ -1,5 +1,6 @@
                i += 1
                while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                    d_line = diff_lines[i]
                    if d_line.startswith(" "):
                        if orig_idx < len(original_lines):
                            patched.append(original_lines[orig_idx])
                            orig_idx += 1
                    elif d_line.startswith("-"):
                        orig_idx += 1
                    elif d_line.startswith("+"):
                        patched.append(d_line[1:])
                    i += 1
                continue
            i += 1

        # Append remaining original lines if any
        if orig_idx < len(original_lines):
            patched.extend(original_lines[orig_idx:])

        return patched if patched else original_lines

    def run_tests_in_sandbox(
        self,
        target_file_rel: str,
        patch_diff: str,
        test_pattern: str | None = None,
    ) -> SandboxResult:
        """
        Copy repo to sandbox, apply patch, execute pytest, and return results.
        Guarantees cleanup of sandbox directory.
        """
        sandbox_dir = self.create_sandbox_env()
        try:
            # Copy essential codebase into sandbox (aegis tree or tests + code)
            src_target = self.root_dir / target_file_rel
            if not src_target.exists():
                # Check relative to root_dir
                src_target = Path(os.path.join(self.root_dir, target_file_rel))

            # Duplicate files needed for pytest execution
            for item in ["connectors", "core", "storage", "extraction", "normalization", "opportunity", "agents", "tests", "pyproject.toml"]:
                source_item = self.root_dir / item
                if source_item.exists():
                    dest_item = sandbox_dir / item
                    if source_item.is_dir():
                        shutil.copytree(source_item, dest_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source_item, dest_item)

            target_in_sandbox = sandbox_dir / target_file_rel
            if not target_in_sandbox.parent.exists():
                target_in_sandbox.parent.mkdir(parents=True, exist_ok=True)

            # Apply patch inside sandbox
            self.apply_patch_to_file(target_in_sandbox, patch_diff)

            # Run pytest in sandbox process
            cmd = [sys.executable, "-m", "pytest"]
            if test_pattern:
                cmd.append(test_pattern)

            env = os.environ.copy()
            env["PYTHONPATH"] = str(sandbox_dir)

            proc = subprocess.run(
                cmd,
                cwd=str(sandbox_dir),
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            success = proc.returncode == 0
            return SandboxResult(
                success=success,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                details={
                    "sandbox_dir": str(sandbox_dir),
                    "target_file": target_file_rel,
                },
            )
        except Exception as exc:
            return SandboxResult(
                success=False,
                exit_code=1,
                stderr=str(exc),
            )
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
