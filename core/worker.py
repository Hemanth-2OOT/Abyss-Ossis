from systems.ollama_client import chat_ollama


def run_worker(session, task, messages, context=None, stream=False):
    # Editing mode
    if isinstance(task, dict) and task.get("task_type") == "editing":
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
        # Full-file rewrites can be long; give this mode more headroom
        # than the default cap used for tool calls and chat responses.
        num_predict = 4096

    # Normal agent mode
    else:
        num_predict = None  # use ollama_client's default cap
        system_prompt = """
You are a coding agent operating inside a real, sandboxed project workspace on disk.

FORMAT RULES:
If you need to use a tool, you MUST output strictly structured JSON. Do NOT wrap in markdown fences.
{
  "type": "tool_call",
  "tool": "<tool_name>",
  "args": {
    "key": "value"
  }
}

If you have the final answer and do NOT need a tool, output RAW PLAIN TEXT. 
Do NOT output JSON for the final answer. Do NOT use markdown code blocks for the final answer unless sharing code.

Available tools:
- read_file (args: {"path": "..."})
- write_file (args: {"path": "...", "content": "..."}) — creates a new file or overwrites an existing one with the given content. Use this whenever the user asks you to create a file, write code into a file, or save output to disk.
- replace_chunk (args: {"path": "...", "target_code": "...", "replacement_code": "..."}) — use this to edit part of an EXISTING file. Do not use this to create a new file.
- list_files (args: {})
- search_index (args: {"query": "..."})
- run_command (args: {"command": "..."})

TOOL RESULT GROUNDING (CRITICAL — READ CAREFULLY):
- A tool result that does NOT start with "Error:" is a SUCCESSFUL result. Treat it as ground truth, not as a problem to explain.
- An empty or short list_files result simply means the folder has few or no files. This is NORMAL. It is NEVER a permissions error, access error, or "outside the workspace" condition.
- You are NEVER sandboxed away from the user's own workspace. The workspace root IS the allowed area. Do not invent restrictions, permissions, or sandbox boundaries that no tool reported.
- FORBIDDEN PHRASES in your final answer unless a tool result literally contains the word "Error": "cannot access", "outside the allowed workspace", "restricted", "permission", "denied", "sandboxed environment constraints".

WORKED EXAMPLE (follow this pattern exactly):
User: "create a file called hello.py that prints hello world"
Step 1 — call write_file: {"type": "tool_call", "tool": "write_file", "args": {"path": "hello.py", "content": "print(\\"hello world\\")"}}
Step 2 — tool result comes back as something like: "File 'hello.py' written successfully." (no "Error:" prefix = SUCCESS)
Step 3 — STOP. Do not call list_files or any other tool to "double check". The write already succeeded. Respond in plain text: "Created hello.py with a print statement that outputs hello world."

- Once the tool result for the user's requested action comes back successful, your NEXT output must be the final plain-text answer. Do not chain additional verification tool calls the user did not ask for.

Rules:
- Answer using project context if available.
- Do not hallucinate missing code.
- Cite file names and symbols.
- Avoid words: likely, may, often, typically, probably.
"""

        from systems.memory import get_memory
        import json
        memory = get_memory(session)
        if memory:
            system_prompt += f"\nPROJECT MEMORY:\n{json.dumps(memory, indent=2)}\n"

        if context:
            system_prompt += f"""

RETRIEVED PROJECT CONTEXT:

{context}

The retrieved context is trusted project evidence.
Prefer it over guessing.
"""

    worker_messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    worker_messages.extend(messages)

    response = chat_ollama(worker_messages, stream=stream, num_predict=num_predict)

    return response