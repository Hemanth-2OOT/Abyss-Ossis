from dataclasses import dataclass, field
from typing import List

@dataclass
class ToolResult:
    success: bool
    stdout: str
    stderr: str = ""
    artifacts: List[str] = field(default_factory=list)
    runtime_verified: bool = False
    is_long_running: bool = False
    status: str = "unknown"
    summary: str = ""
