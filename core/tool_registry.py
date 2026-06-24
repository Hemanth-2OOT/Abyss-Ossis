import os

def normalize_path(path_str: str) -> str:
    if not path_str: return ""
    return os.path.normpath(path_str).replace("\\", "/")

def is_path_match(event_path: str, target_path: str) -> bool:
    if not event_path or not target_path: return False
    ep = normalize_path(event_path)
    tp = normalize_path(target_path)
    if ep == tp: return True
    if ep.endswith("/" + tp) or tp.endswith("/" + ep): return True
    if os.path.basename(ep) == os.path.basename(tp): return True
    return False

from dataclasses import dataclass, field
from typing import Callable, Optional

@dataclass
class ToolSpec:
    description: str
    planner_visible: bool
    mutates_filesystem: bool
    required_args: tuple
    validator: Callable
    argument_validator: Optional[Callable] = None
    requires_existing_file: bool = False
    supports_parallel: bool = False
    estimated_cost: int = 1
    produces_artifacts: list = field(default_factory=list)
    worker_schema: dict = field(default_factory=dict)

class PlannerContractError(Exception):
    pass

def _validate_path_tool(tool_name: str):
    def validator(req, state) -> bool:
        target_norm = normalize_path(req.args.get("path") or req.args.get("file") or req.args.get("filename"))
        valid_events = [e for e in state.tool_events if e.started_at is not None and e.started_at >= (req.started_at or 0.0)]
        return any(
            e.tool == tool_name 
            and e.success 
            and is_path_match(e.args.get("path") or e.args.get("filename") or e.args.get("file"), target_norm) 
            for e in valid_events
        )
    return validator

def _validate_run_command(req, state) -> bool:
    valid_events = [e for e in state.tool_events if e.started_at is not None and e.started_at >= (req.started_at or 0.0)]
    # Could eventually compare req.args.get("command") == e.args.get("command")
    return any(e.tool == "run_command" and e.success for e in valid_events)

def _validate_discovery_tool(tool_name: str):
    def validator(req, state) -> bool:
        valid_events = [e for e in state.tool_events if e.started_at is not None and e.started_at >= (req.started_at or 0.0)]
        return any(e.tool == tool_name and e.success for e in valid_events)
    return validator

TOOL_REGISTRY = {
    "write_file": ToolSpec(
        description="Create or overwrite a file with specific content.",
        planner_visible=True,
        mutates_filesystem=True,
        required_args=("path",),
        validator=_validate_path_tool("write_file"),
        worker_schema={
            "type": "tool_call",
            "tool": "write_file",
            "args": {
                "path": "path/to/file.py",
                "content": "new code string"
            }
        }
    ),
    "replace_chunk": ToolSpec(
        description="Replace a specific block of text in an existing file.",
        planner_visible=True,
        mutates_filesystem=True,
        required_args=("path",),
        validator=_validate_path_tool("replace_chunk"),
        requires_existing_file=True,
        worker_schema={
            "type": "tool_call",
            "tool": "replace_chunk",
            "args": {
                "path": "path/to/file.py",
                "target_code": "old code string",
                "replacement_code": "new code string"
            }
        }
    ),
    "delete_file": ToolSpec(
        description="Delete a file from the filesystem.",
        planner_visible=True,
        mutates_filesystem=True,
        required_args=("path",),
        validator=_validate_path_tool("delete_file"),
        requires_existing_file=True,
        worker_schema={
            "type": "tool_call",
            "tool": "delete_file",
            "args": {
                "path": "path/to/file.py"
            }
        }
    ),
    "read_file": ToolSpec(
        description="Read the contents of a file.",
        planner_visible=True,
        mutates_filesystem=False,
        required_args=("path",),
        validator=_validate_path_tool("read_file"),
        worker_schema={
            "type": "tool_call",
            "tool": "read_file",
            "args": {
                "path": "path/to/file.py"
            }
        }
    ),
    "run_command": ToolSpec(
        description="Execute a shell command.",
        planner_visible=True,
        mutates_filesystem=True,
        required_args=("command",),
        validator=_validate_run_command,
        worker_schema={
            "type": "tool_call",
            "tool": "run_command",
            "args": {
                "command": "python script.py"
            }
        }
    ),
    "search_index": ToolSpec(
        description="Search across all files for a keyword or pattern.",
        planner_visible=True,
        mutates_filesystem=False,
        required_args=(),
        validator=_validate_discovery_tool("search_index"),
        worker_schema={
            "type": "tool_call",
            "tool": "search_index",
            "args": {
                "query": "keyword"
            }
        }
    ),
    "list_files": ToolSpec(
        description="List files in a directory.",
        planner_visible=True,
        mutates_filesystem=False,
        required_args=(),
        validator=_validate_discovery_tool("list_files"),
        worker_schema={
            "type": "tool_call",
            "tool": "list_files",
            "args": {}
        }
    ),
    "patch_file": ToolSpec(
        description="Apply a unified diff patch to a file.",
        planner_visible=False,
        mutates_filesystem=True,
        required_args=("path",),
        validator=_validate_path_tool("patch_file"),
        requires_existing_file=True,
        worker_schema={
            "type": "tool_call",
            "tool": "patch_file",
            "args": {
                "path": "path/to/file.py",
                "diff": "unified diff string"
            }
        }
    )
}

VALID_TOOLS = [name for name, spec in TOOL_REGISTRY.items() if spec.planner_visible]
ALL_WORKER_TOOLS = list(TOOL_REGISTRY.keys())
