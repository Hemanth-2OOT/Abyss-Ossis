from systems.ollama_client import chat_ollama
from config import WORKER_MODEL, EDITOR_MODEL


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
        num_predict = 4096
        model = EDITOR_MODEL

    # Chat / Explanation mode
    elif isinstance(task, dict) and task.get("task_type") in ("chat", "explanation"):
        system_prompt = """
You are a helpful, conversational AI assistant.

Rules:
- Respond directly in RAW PLAIN TEXT format.
- Never output JSON format.
- Never emit 'tool_call', 'print', 'print_message', or 'print_statement'.
- Do not attempt to use any tools. Provide your final answer directly to the user.
"""
        num_predict = 2048
        model = WORKER_MODEL

    # Normal agent mode
    else:
        num_predict = 4096
        model = WORKER_MODEL
        
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

CODING REASONING PROTOCOL:

Before writing or modifying code, internally perform these checks:

1. STATE MODEL
Identify mutable state variables and valid transitions.

2. INVARIANTS
List rules that must always remain true.

Examples:
- snake cannot reverse into itself
- queue size cannot become negative
- authenticated user cannot be None during protected actions

3. EDGE CASES
Check boundary conditions and invalid inputs.

4. FAILURE CHECK
Ask:
"What code would compile but still behave incorrectly?"

Then proceed with tool calls or final answer.

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
            # T3 fix: compact serialisation (no indent) + cap to 20 most-recent
            # entries. indent=2 adds ~30% whitespace tokens for zero benefit to
            # the model. 50-entry dumps were costing ~220 tokens every LLM call.
            _mem_entries = dict(list(memory.items())[-20:])
            system_prompt += f"\nPROJECT MEMORY:\n{json.dumps(_mem_entries)}\n"

        if context:
            system_prompt += f"\nRETRIEVED PROJECT CONTEXT:\n\n{context}\n\nThe retrieved context is trusted project evidence.\nPrefer it over guessing.\n"

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