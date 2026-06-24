from systems.ollama_client import chat_ollama
from config import WORKER_MODEL, EDITOR_MODEL


def run_worker(session, task, messages, context=None, stream=False,
               skill_text: str = "", open_spec=None, worker_mode: str = "chat"):
    """
    Parameters
    ----------
    worker_mode: str
        "execute" -> strict JSON tool_call or final response
        "respond" -> strictly prose final answer
        "chat"    -> standard fast-path conversational mode
        "editing" -> returns only code
    """
    if worker_mode == "editing":
        system_prompt = """
You are a senior code editor.

Modify code exactly as requested.

Rules:
- Return ONLY code.
- No markdown fences.
- No explanations.
- No comments unless requested.
- Output must start with code on line 1.
"""
        num_predict = 4096
        model = EDITOR_MODEL

    elif worker_mode == "chat":
        system_prompt = """You are a helpful, conversational AI assistant. Provide your response directly to the user without any preamble, meta-commentary, or acknowledgment of your instructions."""
        num_predict = 2048
        model = WORKER_MODEL

    elif worker_mode == "respond":
        system_prompt = """
You are a helpful, conversational AI assistant.

You have just finished using tools to complete a user's request. 
Produce the user-facing response summarizing what you did.

Rules:
- Never call tools.
- Never output JSON.
- Output plain prose or markdown explaining the resolution.
"""
        num_predict = 2048
        model = WORKER_MODEL

    elif worker_mode == "execute":
        num_predict = 4096
        model = WORKER_MODEL
        import json
        from core.tool_registry import TOOL_REGISTRY, ALL_WORKER_TOOLS
        schemas_str = ""
        for idx, t_name in enumerate(ALL_WORKER_TOOLS, 1):
            schema = TOOL_REGISTRY[t_name].worker_schema
            schemas_str += f"{idx}. {t_name}\n{json.dumps(schema, indent=2)}\n\n"
        
        system_prompt = f"""
You are an expert, autonomous software engineer.
You are given a user request and must execute it exactly using the available tools.

AVAILABLE TOOLS:
{schemas_str}
Note for replace_chunk: target_code MUST be unique within the file. Include 1-2 lines of surrounding unchanged context if needed to guarantee uniqueness.

If you need to use a tool, return its JSON schema exactly.
If you have completed the edits/task and need no further tools, return:
{{
  "type": "final"
}}

IMPORTANT EXECUTION RULES:
- If your last ToolResult for run_command was success=True, determine if the user's request is already satisfied. If yes, output {{"type": "final"}}.
- Do NOT repeat the exact same run_command consecutively unless the user explicitly requested retries.

CRITICAL:
You must never invent tool names. Use ONLY the available tools listed above.
"""
        
        task_type = task.get("task_type", "coding")
        if task_type == "execute":
            # Derive real Python file list from workspace so worker never invents filenames
            try:
                from core.execution_state import ExecutionState as _ES
                _py_files = _ES(task_type="execute").workspace_python_files(
                    cwd=session.root if hasattr(session, "root") else "."
                )
                if _py_files:
                    _file_list_str = "\n".join(f"  - {f}" for f in _py_files)
                    system_prompt += (
                        f"\nTASK TYPE: EXECUTE\n"
                        f"Preferred tool: run_command\n"
                        f"Do NOT edit files unless explicitly requested.\n\n"
                        f"WORKSPACE PYTHON FILES (use one of these - do NOT invent filenames):\n"
                        f"{_file_list_str}\n\n"
                        f"If asked to run/start/launch a backend or server, pick the most likely entry point "
                        f"from the list above. If uncertain, call list_files first.\n"
                    )
                else:
                    system_prompt += (
                        "\nTASK TYPE: EXECUTE\nPreferred tool: run_command\n"
                        "Do NOT edit files unless explicitly requested.\n"
                        "Call list_files first to discover the entry point before running python.\n"
                    )
            except Exception:
                system_prompt += "\nTASK TYPE: EXECUTE\nPreferred tool: run_command\nDo NOT edit files unless explicitly requested.\n"

        elif task_type == "coding":
            system_prompt += """
TASK TYPE: CODING

Think like a senior software engineer. Do not make isolated edits. Understand the architecture first. Every code change should be consistent with the whole project. Favor correctness over minimal edits.


Before editing any file you MUST understand the project. Never edit after reading only one file if the feature spans multiple files.

REQUIRED 5-PHASE WORKFLOW:
Phase 1: Explore. Discover and read every file that affects the requested feature. (e.g. If editing index.html, read style.css, the backend routes, and JS).
Phase 2: Plan internally. Build an internal understanding and dependency graph.
Phase 3: Edit. Perform your planned edits.
Phase 4: Self-Review. Check: Did I modify every file required? Did I forget backend changes? Do routes match? Do variables exist? Will it compile?
Phase 5: Final. Only emit 'final' if all answers are satisfactory.

EDITING RULES (FILE SIZE STRATEGY):
- 0-400 lines: MUST use `read_file` followed by `write_file` to completely rewrite the file.
- 401-1000 lines: Use `replace_chunk`.
- 1000+ lines: Use precise `replace_chunk` patches only.
- Reason internally before producing tool calls. Do not expose your internal reasoning or scratchpad.

INTENT-BASED EXPANSION:
Automatically expand your goals based on the user's intent:
- 'Improve UI' -> layout, spacing, colors, typography, responsiveness, accessibility, hover effects.
- 'Refactor' -> readability, duplicate removal, naming, preserve behavior.
- 'Optimize' -> performance, unnecessary loops, allocations, complexity.
- 'Fix bug' -> identify root cause, minimal patch, preserve behavior, verify affected files.
Do not stop after cosmetic or 3-line changes. Aim for a complete, professional implementation.
"""
        elif task_type == "file_analysis":
            system_prompt += "\nTASK TYPE: FILE ANALYSIS\nPreferred tools: read_file, list_files. Do not edit files.\n"

        from systems.memory import get_memory
        import json
        memory = get_memory(session)
        if memory:
            _mem_entries = dict(list(memory.items())[-20:])
            system_prompt += f"\nPROJECT MEMORY:\n{json.dumps(_mem_entries)}\n"

        if context:
            system_prompt += f"\nRETRIEVED PROJECT CONTEXT:\n\n{context}\n\nThe retrieved context is trusted project evidence.\nPrefer it over guessing.\n"

        if open_spec is not None:
            system_prompt += f"\n\n{open_spec.render()}\n"

        if skill_text:
            system_prompt += (
                f"\n\nRELEVANT SKILLS:\n"
                f"The following are reference guidelines and best practices. "
                f"They are NOT executable tools. Do NOT emit tool calls for these skills.\n\n"
                f"{skill_text}\n"
            )

    worker_messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    for m in messages:
        worker_messages.append({
            "role": m.get("role", "user"),
            "content": m.get("content", "")
        })

    response = chat_ollama(
        worker_messages,
        model=model,
        stream=stream,
        num_predict=num_predict
    )
    return response