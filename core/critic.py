from systems.ollama_client import chat_ollama


def critique_response(
    user_input,
    response,
    retrieval_used=False,
    match_count=0,
    context=""
):
    """
    Returns:
        OK
        NEEDS_MORE_INFO
    """

    # Fast-path for retrieval-backed lookup questions
    if retrieval_used and match_count > 0:
        lookup_words = [
            "where is",
            "defined",
            "which file",
            "who calls",
            "find",
            "locate"
        ]

        lower_input = user_input.lower()

        if any(word in lower_input for word in lookup_words):
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

Return NEEDS_MORE_INFO if:
- debugging without code/logs/errors
- coding request missing requirements
- file analysis without file content
- assistant makes assumptions
- retrieval exists but answer ignores retrieved evidence

Return OK only if enough evidence exists.

Output ONE WORD ONLY.
"""

    context_preview = context[:1000] if context else ""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": f"""
User Question:
{user_input}

Assistant Response:
{response}

Retrieval Used:
{retrieval_used}

Context Matches:
{match_count}

Retrieved Context:
{context_preview}
"""
        }
    ]

    try:
        result = chat_ollama(messages).strip().upper()

        if result == "OK":
            return "OK"

        return "NEEDS_MORE_INFO"

    except Exception:
        # Fail open rather than blocking the user
        return "OK"