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


from enum import Enum

class RequirementStatus(Enum):
    NEW = "NEW"
    BLOCKED = "BLOCKED"
    READY = "READY"
    ACTIVE = "ACTIVE"
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"

@dataclass
class Requirement:
    id: str
    type: str
    args: dict = field(default_factory=dict)
    _status: RequirementStatus = field(default=RequirementStatus.NEW, repr=False)
    metadata: dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    origin: str = "planner"
    state_transitions: List[str] = field(default_factory=list)
    started_at: float | None = field(default=None, repr=False)
    finished_at: float | None = field(default=None, repr=False)
    reasoning_calls: int = 0
    tool_calls: int = 0
    validator_failures: int = 0
    planner_regenerations: int = 0

    @property
    def status(self) -> RequirementStatus:
        return self._status

    @status.setter
    def status(self, new_status: RequirementStatus):
        import time
        if self._status == new_status:
            return
        self._status = new_status
        self.state_transitions.append(new_status.name)
        
        if new_status == RequirementStatus.ACTIVE:
            self.finished_at = None
            if self.started_at is None:
                self.started_at = time.time()
            
        if new_status in (RequirementStatus.FAILED, RequirementStatus.SATISFIED):
            self.finished_at = time.time()

    @property
    def time_elapsed_seconds(self) -> float:
        import time
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)

    def __post_init__(self):
        if not self.state_transitions:
            self.state_transitions.append(self._status.name)

@dataclass
class FileSnapshot:
    path: str
    content: str
    sha256: str
    version: int
    dirty: bool
    exists: bool
    last_modified_pass: int


@dataclass
class ExecutionState:
    task_type: str
    user_prompt: str = ""
    requirements: List[Requirement] = field(default_factory=list)
    tool_events: List[ToolEvent] = field(default_factory=list)
    files_read: Set[str] = field(default_factory=set)
    file_relationships: dict = field(default_factory=dict)
    commands_run: List[str] = field(default_factory=list)
    hallucinated_tool_count: int = 0
    hallucinated_tool_names: List[str] = field(default_factory=list)
    parse_retries: int = 0
    validation_retries: int = 0
    file_cache: dict[str, 'FileSnapshot'] = field(default_factory=dict)

    @property
    def files_written(self) -> Set[str]:
        return {p for p, snap in self.file_cache.items() if snap.dirty}

    def update_snapshot(self, path: str, content: str, exists: bool, current_pass: int):
        import hashlib
        import os
        norm_path = os.path.normpath(path).replace("\\", "/")
        sha256 = hashlib.sha256(content.encode('utf-8')).hexdigest() if content else ""
        
        if norm_path in self.file_cache:
            snap = self.file_cache[norm_path]
            if snap.sha256 != sha256 or snap.exists != exists:
                snap.content = content
                snap.sha256 = sha256
                snap.version += 1
                snap.dirty = True
                snap.exists = exists
                snap.last_modified_pass = current_pass
        else:
            self.file_cache[norm_path] = FileSnapshot(
                path=norm_path,
                content=content,
                sha256=sha256,
                version=1,
                dirty=False,
                exists=exists,
                last_modified_pass=current_pass
            )

    def get_snapshot(self, path: str) -> 'FileSnapshot | None':
        import os
        norm_path = os.path.normpath(path).replace("\\", "/")
        return self.file_cache.get(norm_path)

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
