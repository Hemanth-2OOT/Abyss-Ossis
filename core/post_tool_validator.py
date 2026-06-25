from typing import Dict, List, Any
from .execution_state import ExecutionState, RequirementStatus

def normalize_path(path_str: str) -> str:
    import os
    if not path_str: return ""
    return os.path.normpath(path_str).replace("\\", "/")

def is_path_match(event_path: str, target_path: str) -> bool:
    if not event_path or not target_path: return False
    ep = normalize_path(event_path)
    tp = normalize_path(target_path)
    if ep == tp: return True
    if ep.endswith("/" + tp) or tp.endswith("/" + ep): return True
    import os
    if os.path.basename(ep) == os.path.basename(tp): return True
    return False

from core.tool_registry import TOOL_REGISTRY, PlannerContractError

def evaluate_requirement_satisfied(req, state: ExecutionState) -> bool:
    req_type = req.type.lower()
    
    cfg = TOOL_REGISTRY.get(req_type)
    if cfg is None:
        raise PlannerContractError(f"Unknown requirement type in execution: {req.type}")
        
    validator = cfg.validator
    if validator is None:
        return False
        
    return validator(req, state)


def update_scheduler_state(state: ExecutionState, final_declared: bool = False) -> tuple[bool, str]:
    """
    Evaluates the dependency graph, updates requirement states, and formats the active task.
    Returns (is_finished, prompt_injection_string)
    
    Legal State Transitions:
    - NEW -> READY (when all depends_on are SATISFIED)
    - NEW -> BLOCKED (if depends_on has FAILED)
    - READY -> ACTIVE (when selected for execution)
    - ACTIVE -> SATISFIED (when evaluate_requirement_satisfied is True)
    - ACTIVE -> FAILED (ONLY if final_declared is True and it remains unsatisfied)
    - ACTIVE -> ACTIVE (while work is in progress)
    """
    if not state.requirements:
        # Fallback for tasks with no structured requirements
        return False, ""

    # 1. Update satisfaction for ACTIVE requirements
    for req in state.requirements:
        if req.status == RequirementStatus.ACTIVE:
            if evaluate_requirement_satisfied(req, state):
                req.status = RequirementStatus.SATISFIED
            elif final_declared:
                req.status = RequirementStatus.FAILED

    # 2. Re-evaluate dependencies for NEW, BLOCKED, FAILED
    satisfied_ids = {r.id for r in state.requirements if r.status == RequirementStatus.SATISFIED}
    
    for req in state.requirements:
        if req.status in (RequirementStatus.NEW, RequirementStatus.BLOCKED):
            if all(dep in satisfied_ids for dep in req.depends_on):
                req.status = RequirementStatus.READY
            else:
                req.status = RequirementStatus.BLOCKED

    # 3. Find/Set ACTIVE requirement
    active_req = next((r for r in state.requirements if r.status == RequirementStatus.ACTIVE), None)
    if not active_req:
        active_req = next((r for r in state.requirements if r.status == RequirementStatus.READY), None)
        if active_req:
            active_req.status = RequirementStatus.ACTIVE

    # 4. Check if finished
    if all(r.status == RequirementStatus.SATISFIED for r in state.requirements):
        return True, ""

    if not active_req:
        return False, "Validation Failed: No READY requirements available but tasks are not fully satisfied. Check for circular dependencies or blocked tasks."

    clean_args = {}
    for k, v in active_req.args.items():
        if isinstance(v, str) and ("{" in v or "}" in v or "<" in v or ">" in v):
            continue
        clean_args[k] = v

    import json
    req_json = {
        "id": active_req.id,
        "type": active_req.type,
        "args": clean_args
    }
    
    msg = (
        f"CURRENT ACTIVE REQUIREMENT:\n```json\n{json.dumps(req_json, indent=2)}\n```\n\n"
        f"ACTION REQUIRED: You MUST execute this requirement NOW. Output the corresponding tool call JSON to fulfill it. "
        f"If the args are empty, you MUST infer the concrete values from the conversation history before calling the tool. Do NOT output 'final' until this tool has been executed and succeeded."
    )
    return False, msg
