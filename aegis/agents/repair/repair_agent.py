"""
Aegis — Repair Agent

Generates minimal, unified diff code patches for broken connectors while strictly
isolating LLM prompt contexts and defending against prompt injection in untrusted web text.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from core.schemas.domain import FailureClass


class RepairAgent:
    """Agent responsible for diagnosing connector code and synthesizing unified diff patches."""

    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"system\s+instruction\s+override", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
        re.compile(r"execute\s+command", re.IGNORECASE),
        re.compile(r"rm\s+-rf", re.IGNORECASE),
    ]

    def sanitize_untrusted_content(self, raw_text: str) -> str:
        """
        Sanitize untrusted HTML/snapshot text before including it in an LLM prompt.
        Strips script/style tags, HTML comments, and potential prompt injection triggers.
        """
        if not raw_text:
            return ""

        # Remove script and style elements
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML comments
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

        # Defuse prompt injection keywords
        for pattern in self.INJECTION_PATTERNS:
            cleaned = pattern.sub("[REDACTED_INJECTED_INSTRUCTION]", cleaned)

        # Limit snapshot context size to prevent token flooding
        return cleaned[:8000]

    def build_scoped_prompt(
        self,
        connector_code: str,
        sanitized_snapshot: str,
        error_summary: str,
        failure_class: FailureClass | str,
    ) -> str:
        """
        Construct a strictly scoped prompt context for patch generation.
        Excludes repository credentials, secrets, or unrelated domain files.
        """
        failure_str = failure_class.value if isinstance(failure_class, FailureClass) else failure_class
        prompt = (
            f"You are a specialized connector repair agent.\n"
            f"Target Failure: {failure_str}\n"
            f"Error Details: {error_summary}\n\n"
            f"RULES:\n"
            f"1. Propose ONLY a minimal unified diff patch for the provided connector source code.\n"
            f"2. Do NOT rewrite the entire file.\n"
            f"3. Do NOT add imported shell execution modules or system commands.\n"
            f"4. Focus only on fixing selector, parsing, or schema extraction logic.\n\n"
            f"=== CONNECTOR SOURCE CODE ===\n{connector_code}\n\n"
            f"=== SANITIZED PAGE SNAPSHOT ===\n{sanitized_snapshot}\n"
        )
        return prompt

    def generate_unified_diff(
        self,
        target_file_rel: str,
        original_code: str,
        patched_code: str,
    ) -> str:
        """Create a clean unified diff string between original and patched code."""
        orig_lines = original_code.splitlines(keepends=True)
        patch_lines = patched_code.splitlines(keepends=True)

        diff_gen = difflib.unified_diff(
            orig_lines,
            patch_lines,
            fromfile=f"a/{target_file_rel}",
            tofile=f"b/{target_file_rel}",
        )
        return "".join(diff_gen)

    def synthesize_fallback_patch(
        self,
        target_file_rel: str,
        source_code: str,
        failure_class: FailureClass | str,
        broken_selector: str | None = None,
        fixed_selector: str | None = None,
    ) -> str:
        """
        Rule-based diff synthesizer for deterministic self-healing demos and offline operation.
        Replaces broken CSS/XPath selectors or fallback logic cleanly with updated selectors.
        """
        if broken_selector and fixed_selector and broken_selector in source_code:
            patched_code = source_code.replace(broken_selector, fixed_selector)
            return self.generate_unified_diff(target_file_rel, source_code, patched_code)

        # Common rule-based fallback patches
        patched_code = source_code
        if "h1.opportunity-title" in source_code:
            patched_code = source_code.replace("h1.opportunity-title", "h1.event-title, h1.opportunity-title, h1")
        elif "span.deadline-date" in source_code:
            patched_code = source_code.replace("span.deadline-date", "span.deadline-date, span.date, time")

        return self.generate_unified_diff(target_file_rel, source_code, patched_code)
