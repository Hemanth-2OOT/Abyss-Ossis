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
        system_prompt = """
You are a helpful, conversational AI assistant.

Rules:
- Respond directly in RAW PLAIN TEXT format.
- Never output JSON format.
- Never emit tools.
- Provide your final answer directly to the user.
"""
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

        system_prompt = """
You are a coding agent operating inside a real, sandboxed project workspace on disk.

You are in EXECUTE mode.
You may ONLY return one single valid JSON object.
Legal outputs: 'tool_call' or 'final'.
Nothing else. No markdown. No explanation. No code fences. No reasoning.

AVAILABLE TOOLS

1. read_file
{
  "type": "tool_call",
  "tool": "read_file",
  "args": {
      "path": "templates/index.html"
  }
}

2. write_file
{
  "type": "tool_call",
  "tool": "write_file",
  "args": {
      "path": "templates/index.html",
      "content": "new file content here"
  }
}

3. replace_chunk
{
  "type": "tool_call",
  "tool": "replace_chunk",
  "args": {
      "path": "templates/index.html",
      "target_code": "old code string",
      "replacement_code": "new code string"
  }
}

4. list_files
{
  "type": "tool_call",
  "tool": "list_files",
  "args": {}
}

5. run_command
{
  "type": "tool_call",
  "tool": "run_command",
  "args": {
      "command": "python script.py"
  }
}

If you need to use a tool, return its JSON schema exactly.
If you have completed the edits/task and need no further tools, return:
{
  "type": "final"
}

IMPORTANT EXECUTION RULES:
- If your last ToolResult for run_command was success=True, determine if the user's request is already satisfied. If yes, output {"type": "final"}.
- Do NOT repeat the exact same run_command consecutively unless the user explicitly requested retries.
"""
        
        task_type = task.get("task_type", "coding")
        if task_type == "execute":
            # Derive real Python file list from workspace so worker never invents filenames
            try:
                from core.execution_state import ExecutionState as _ES
                from core.session import ProjectSession as _PS
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
            system_prompt += "\nTASK TYPE: CODING\nUse editing tools (write_file, replace_chunk) to fulfill the requirements.\n"
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