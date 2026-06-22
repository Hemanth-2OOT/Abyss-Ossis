from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class ToolEvent:
    tool: str
    args: dict
    success: bool
    started_at: float
    finished_at: float
    result_summary: str
    status: str = "completed"
    is_long_running: bool = False
    stdout: str = ""
    error: str | None = None


@dataclass
class ExecutionState:
    task_type: str
    tool_events: List[ToolEvent] = field(default_factory=list)
    files_read: Set[str] = field(default_factory=set)
    files_written: Set[str] = field(default_factory=set)
    commands_run: List[str] = field(default_factory=list)
    completed_contracts: Set[str] = field(default_factory=set)
    artifacts: List[str] = field(default_factory=list)
    runtime_verified: bool = False
    finished: bool = False

    def workspace_python_files(self, cwd: str = ".") -> List[str]:
        """
        Returns a sorted list of .py files in the workspace.
        Used by the execute-mode worker to avoid inventing filenames.
        """
        import os
        results = []
        for root, dirs, files in os.walk(cwd):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "__pycache__", ".venv", "venv", "node_modules"}
            ]
            for f in files:
                if f.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, f), cwd)
                    results.append(rel.replace("\\", "/"))
        return sorted(results)[:30]

    def render_transcript(self) -> str:
        lines = ["Execution Summary\n"]
        if self.files_read:
            lines.append("Read:")
            for f in sorted(self.files_read):
                lines.append(f"  ✓ {f}")
            lines.append("")

        if self.files_written:
            lines.append("Edited:")
            for f in sorted(self.files_written):
                lines.append(f"  ✓ {f}")
            lines.append("")

        if self.commands_run:
            lines.append("Executed:")
            for c in self.commands_run:
                lines.append(f"  ✓ {c}")
            lines.append("")

        errors = [e.error for e in self.tool_events if not e.success and e.error]
        if errors:
            lines.append("Errors:")
            for err in errors:
                lines.append(f"  - {err}")
        else:
            lines.append("Errors: None")

        return "\n".join(lines)
