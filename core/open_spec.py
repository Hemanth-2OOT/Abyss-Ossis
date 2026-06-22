"""
core/open_spec.py
=================
Generates a lightweight internal OpenSpec for coding/debugging tasks.

The spec is represented as a dataclass for future validation use,
then rendered to a compact text block for the worker system prompt.

The spec is NOT displayed to the user by default.
Set the environment variable  DEBUG=1  to print it in cli.py.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OpenSpec:
    goal: str
    constraints: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)

    def render(self) -> str:
        """Render the spec as a compact text block for the system prompt."""
        lines = [
            "INTERNAL SPEC",
            f"Goal: {self.goal}",
        ]
        if self.constraints:
            lines.append("Constraints:")
            for c in self.constraints:
                lines.append(f"  - {c}")
        if self.acceptance:
            lines.append("Acceptance Criteria:")
            for a in self.acceptance:
                lines.append(f"  - {a}")
        return "\n".join(lines)


# ── Keyword-based inference helpers ───────────────────────────────────────────

def _infer_constraints(user_input: str) -> List[str]:
    constraints: List[str] = []
    text = user_input.lower()

    if any(w in text for w in ["flask", "django", "jinja", "template"]):
        constraints.append("Preserve Flask/Jinja template syntax ({{ }}, {% %})")
    if any(w in text for w in ["don't change", "do not change", "keep", "preserve"]):
        constraints.append("Preserve existing functionality — do not remove features")
    if any(w in text for w in ["backend", "server", "api", "route"]):
        constraints.append("Do not modify backend logic or API routes unless explicitly asked")
    if any(w in text for w in ["no test", "don't run", "no need to test"]):
        constraints.append("Do not run tests or benchmarks")
    if "css" in text or "style" in text:
        constraints.append("Use CSS custom properties for colours and spacing")
    if not constraints:
        constraints.append("Preserve all existing functionality")

    return constraints


def _infer_acceptance(user_input: str) -> List[str]:
    acceptance: List[str] = []
    text = user_input.lower()

    if any(w in text for w in ["fix", "bug", "error", "traceback"]):
        acceptance.append("The specific error no longer occurs")
        acceptance.append("Existing behaviour is unchanged")
    if any(w in text for w in ["improve", "better", "enhance", "redesign"]):
        acceptance.append("Visual or structural improvement is visible")
    if any(w in text for w in ["responsive", "mobile"]):
        acceptance.append("Layout is functional on mobile (320px) and desktop (1200px)")
    if any(w in text for w in ["accessible", "accessibility", "aria"]):
        acceptance.append("Page passes basic accessibility checks (labels, alt text, contrast)")
    if any(w in text for w in ["create", "build", "generate", "write"]):
        acceptance.append("All required files are created with correct content")
    if any(w in text for w in ["refactor", "clean", "optimize"]):
        acceptance.append("No behaviour change — refactor only")
        acceptance.append("Code is shorter or more readable than before")
    if not acceptance:
        acceptance.append("Task is completed as described")

    return acceptance


# ── File reference extraction ─────────────────────────────────────────────────

_FILE_PATTERN = re.compile(
    r"\b[\w./\\-]+\.(py|js|ts|html|css|json|yaml|yml|md|txt|toml|cfg|ini|sh)\b",
    re.IGNORECASE
)


def _extract_file_targets(user_input: str) -> List[str]:
    """Return file paths mentioned in the user prompt."""
    return list(dict.fromkeys(_FILE_PATTERN.findall(user_input)))


# ── Public API ────────────────────────────────────────────────────────────────

_SKIP_TYPES = {"chat", "explanation", "lookup"}


def build_open_spec(user_input: str, task: dict) -> Optional[OpenSpec]:
    """
    Build and return an OpenSpec for the current task.

    Returns None for chat/explanation tasks (zero cost on fast path).
    """
    task_type = task.get("task_type", "")
    if task_type in _SKIP_TYPES:
        return None

    # Derive a concise goal from the user input (first 120 chars)
    goal = user_input.strip()
    if len(goal) > 120:
        goal = goal[:117] + "..."

    # Mention target files in the goal if any
    files = _FILE_PATTERN.findall(user_input)
    unique_files = list(dict.fromkeys(files))
    if unique_files:
        goal = f"{goal}  [targets: {', '.join(unique_files[:3])}]"

    spec = OpenSpec(
        goal=goal,
        constraints=_infer_constraints(user_input),
        acceptance=_infer_acceptance(user_input),
    )
    return spec
