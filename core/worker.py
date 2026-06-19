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

    # Normal agent mode
    else:
        system_prompt = """
You are a coding agent.

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
- replace_chunk (args: {"path": "...", "target_code": "...", "replacement_code": "..."})
- list_files (args: {})
- search_index (args: {"query": "..."})
- run_command (args: {"command": "..."})

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

    response = chat_ollama(worker_messages, stream=stream)

    return response