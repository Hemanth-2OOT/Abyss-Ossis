from enum import Enum

class Phase(str, Enum):
    DISCOVERY = "Discovery"
    INVESTIGATION = "Investigation"
    IMPLEMENTATION = "Implementation"
    VERIFICATION = "Verification"

class FSMTracker:
    def __init__(self):
        self.completed_phases = set()

    def mark_event(self, tool_name: str, result_success: bool = True):
        if not result_success:
            return

        if tool_name == "list_files":
            self.completed_phases.add(Phase.DISCOVERY)
        elif tool_name in ("read_file", "search_index"):
            self.completed_phases.add(Phase.INVESTIGATION)
        elif tool_name == "write_file":
            self.completed_phases.add(Phase.IMPLEMENTATION)
        elif tool_name == "run_command":
            self.completed_phases.add(Phase.VERIFICATION)

    def can_transition(self, tool_name: str, tool_args: dict) -> tuple[bool, str]:
        """
        Validates whether a tool execution is allowed under current state.
        Returns (is_allowed, error_message)
        """
        if tool_name == "run_command" and Phase.IMPLEMENTATION not in self.completed_phases:
            cmd = tool_args.get("command", "").lower()
            if "pytest" in cmd or "test" in cmd:
                return False, "Validation attempted before any modifications were made. If the task requires a fix, complete the implementation before rerunning tests."
        
        # Future rules can be added here
        return True, ""

    def render_progress(self) -> str:
        lines = [
            "\n=== TASK PROGRESS TRACKER ===",
            f"[{'✓' if Phase.DISCOVERY in self.completed_phases else ' '}] Discovery",
            f"[{'✓' if Phase.INVESTIGATION in self.completed_phases else ' '}] Investigation",
            f"[{'✓' if Phase.IMPLEMENTATION in self.completed_phases else ' '}] Implementation",
            f"[{'✓' if Phase.VERIFICATION in self.completed_phases else ' '}] Verification",
            "============================="
        ]
        return "\n".join(lines)
