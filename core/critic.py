from systems.ollama_client import chat_ollama


# Tool names whose successful execution means the task is complete.
# Don't send these to the critic — a successful write IS the answer.
_WRITE_TOOLS = {"write_file", "replace_chunk"}


def critique_response(
    user_input,
    response,
    retrieval_used=False,
    match_count=0,
    context="",
    last_tool_name=None,
    last_tool_result=None,
):
    """
    Returns: "OK" or "NEEDS_MORE_INFO"

    Short-circuits to OK when:
    - A write/replace tool succeeded (task is done by definition)
    - Retrieval was used for a lookup-style question
    """

    # ── Short-circuit 1: successful file write ────────────────────────────
    # The critic never sees tool results directly — it only sees the model's
    # prose summary, which is often vague ("Created main.py..."). That's
    # enough for a 7B critic to flag NEEDS_MORE_INFO even on success.
    # Solution: bypass the critic entirely when a write tool succeeded.
    if (
        last_tool_name in _WRITE_TOOLS
        and last_tool_result is not None
        and not str(last_tool_result).startswith("Error:")
    ):
        return "OK"

    # ── Short-circuit 2: retrieval-backed lookup ──────────────────────────
    if retrieval_used and match_count > 0:
        lookup_words = ["where is", "defined", "which file", "who calls", "find", "locate"]
        if any(w in user_input.lower() for w in lookup_words):
            return "OK"

    system_prompt = """
You are a strict critic agent.

Your job is to determine whether the assistant's answer is supported by available evidence.

Return ONLY one of:

OK

NEEDS_MORE_INFO

Rules:

If retrieval_used=True and context_matches > 0:
- Assume relevant code or files were already retrieved.
- Do NOT ask for code again.
- Check whether the answer uses the retrieved evidence.

Return NEEDS_MORE_INFO ONLY if:
- debugging request has no code, logs, or errors to work from
- coding request is missing core requirements
- file analysis requested but no file content was provided
- assistant's answer directly contradicts the retrieved context

Return OK if:
- A file was written or edited successfully
- The assistant's answer is consistent with the retrieved context
- The answer directly addresses the user's question

Output ONE WORD ONLY: OK or NEEDS_MORE_INFO
"""

    context_preview = context[:1000] if context else ""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"User Question:\n{user_input}\n\n"
                f"Assistant Response:\n{response}\n\n"
                f"Retrieval Used:\n{retrieval_used}\n\n"
                f"Context Matches:\n{match_count}\n\n"
                f"Retrieved Context:\n{context_preview}"
            ),
        },
    ]

    try:
        result = chat_ollama(messages).strip().upper()
        if result == "OK":
            return "OK"
        return "NEEDS_MORE_INFO"
    except Exception:
        return "OK"  # fail open