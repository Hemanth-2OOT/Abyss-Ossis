import json
import os
import datetime
from .execution_state import ExecutionState

from typing import Any

def classify_outcome(exec_state: ExecutionState, validation_success: bool, passes: int, max_passes: int, tool_loops: int, max_tool_loops: int, parse_fail_count: int, termination_reason: str) -> str:
    """
    Deterministically evaluates the task history to classify the outcome.
    """
    if termination_reason == "PLANNER_CONTRACT_ERROR":
        return "PLANNER_CONTRACT_ERROR"
        
    if not exec_state.requirements and exec_state.task_type == "coding":
        # If it's a coding task and no requirements were extracted, planner failed
        return "PLANNER_ERROR"
        
    if parse_fail_count >= 5:
        return "WORKER_ERROR"
        
    if exec_state.task_type == "coding" and not validation_success and (tool_loops >= max_tool_loops or passes >= max_passes):
        # Time ran out, but specifically because validation was failing at the end
        return "VALIDATION_ERROR"
        
    if tool_loops >= max_tool_loops or passes >= max_passes:
        return "EXECUTION_TIMEOUT"
        
    # Check tool history
    for event in reversed(exec_state.tool_events):
        if not event.success:
            if "duplicate" in str(event.error).lower():
                return "DUPLICATE_TOOL_CALL"
            if "filenotfound" in str(event.error).lower() or "no such file" in str(event.error).lower():
                return "HALLUCINATED_PATH"
            # Generic tool error
            return "TOOL_ERROR"

    if exec_state.task_type in ("coding", "execute", "file_analysis") and tool_loops == 0 and not exec_state.tool_events:
        return "NO_ACTION"

    if exec_state.task_type in ("chat", "explanation"):
        return "SUCCESS"

    if not validation_success and exec_state.task_type == "coding":
        # User/Model aborted manually during a failed validation state
        return "VALIDATION_ERROR"

    return "SUCCESS"

def record_task(
    exec_state: ExecutionState,
    task_duration: float,
    metrics: Any,
    validation_success: bool,
    models: dict,
    termination_reason: str
):
    """
    Appends a JSONL telemetry record.
    """
    t_start = datetime.datetime.utcnow()

    outcome = classify_outcome(exec_state, validation_success, metrics.reasoning_passes, metrics.max_reasoning_passes, metrics.tool_calls, metrics.max_tool_calls, metrics.parse_retries, termination_reason)
    
    req_payloads = []
    for r in exec_state.requirements:
        req_payloads.append({
            "id": r.id,
            "type": r.type,
            "args": r.args,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "state_transitions": r.state_transitions,
            "time_elapsed_seconds": round(r.time_elapsed_seconds, 2),
            "reasoning_calls": r.reasoning_calls,
            "tool_calls": r.tool_calls,
            "validator_failures": r.validator_failures,
            "planner_regenerations": r.planner_regenerations
        })
        
    t_end = datetime.datetime.utcnow()
    telemetry_time = (t_end - t_start).total_seconds()

    record = {
        "schema_version": 1,
        "timestamp": t_end.isoformat() + "Z",
        "user_request": exec_state.user_prompt,
        "task_type": exec_state.task_type,
        "models": models,
        "requirements": req_payloads,
        "tool_sequence": [e.tool for e in exec_state.tool_events],
        "files_read": list(exec_state.files_read),
        "termination_reason": termination_reason,
        "failure_category": outcome,
        "assistant_status": outcome,
        "total_reasoning_passes": metrics.reasoning_passes,
        "total_tool_calls": metrics.tool_calls,
        "worker_parse_failures": metrics.parse_retries,
        "validation_retries": metrics.validation_retries,
        "planner_regenerations": metrics.planner_regenerations,
        "hallucinated_tool_count": exec_state.hallucinated_tool_count,
        "hallucinated_tool_names": exec_state.hallucinated_tool_names,
        "execution_time_seconds": round(task_duration, 2),
        "planner_time": round(metrics.planner_time, 2),
        "worker_time": round(metrics.worker_time, 2),
        "tool_time": round(metrics.tool_time, 2),
        "validation_time": round(metrics.validation_time, 2),
        "telemetry_time": round(telemetry_time, 2),
        "planner_used": exec_state.task_type == "coding",
        "worker_used": True,
        "validator_used": exec_state.task_type == "coding",
        "scheduler_used": exec_state.task_type == "coding",
        "discovery_used": any(r.type in ("search_index", "list_files") for r in exec_state.requirements)
    }
    
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
        
    with open(os.path.join(log_dir, "telemetry.jsonl"), "a") as f:
        f.write(json.dumps(record) + "\n")
