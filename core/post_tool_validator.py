from typing import Dict, List, Any
from .execution_state import ExecutionState

class TaskContract:
    def __init__(self, requires_any: List[str]):
        self.requires_any = requires_any

    def validate(self, state: ExecutionState) -> tuple[bool, str]:
        if not self.requires_any:
            return True, ""
            
        successful_runs = [
            e.tool for e in state.tool_events
            if e.tool in self.requires_any and e.success is True
        ]
        if successful_runs:
            return True, ""
            
        return False, f"Task contract failed: Requires at least one successful execution of {self.requires_any}. None found in execution state."

TASK_CONTRACTS: Dict[str, TaskContract] = {
    "coding": TaskContract(requires_any=["write_file", "replace_chunk", "patch_file"]),
    "file_analysis": TaskContract(requires_any=["read_file", "list_files", "search_files"]),
    "explanation": TaskContract(requires_any=[]),
    "chat": TaskContract(requires_any=[]),
    "execute": TaskContract(requires_any=["run_command"])
}

def validate_post_tool(state: ExecutionState) -> tuple[bool, str]:
    """
    Validates if the ExecutionState fulfills the Task Contract for its task_type.
    """
    contract = TASK_CONTRACTS.get(state.task_type)
    if not contract:
        # If no strict contract, default to pass to avoid breaking arbitrary tasks
        return True, ""
        
    return contract.validate(state)
