from systems.ollama_client import chat_ollama
from config import CRITIC_MODEL




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

    B8 fix: removed blind short-circuit that returned OK any time write_file
    succeeded. A file can be written with syntactically valid but semantically
    wrong code — the LLM critic must still verify the content addresses the
    user's request. write_file success is now passed as evidence to the prompt
    so the LLM can weigh it, but does not bypass evaluation entirely.
    """

    system_prompt = """
You are a critic agent reviewing an assistant's proposed response or action against available evidence.

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
- coding request is missing core requirements (e.g. wrote empty file, wrong filename)
- file analysis requested but no file content was provided
- assistant's answer directly contradicts the retrieved context
- a file was written but its content clearly does not address the user's request

Return OK if:
- The assistant's answer is consistent with the retrieved context AND addresses the request
- A file was successfully written AND its content plausibly addresses the user's request
- The answer directly and completely addresses the user's question

Output ONE WORD ONLY: OK or NEEDS_MORE_INFO
"""

    # T4 fix: critic only needs to assess intent, not read every line of code.
    # Truncate response to 800 chars (~200 tokens). Full 4096-token responses
    # were billing the critic the same cost as the worker for a yes/no decision.
    response_preview = response[:800] if len(response) > 800 else response

    # Only include retrieved context when it was actually used — otherwise it
    # adds ~250 tokens for evidence that played no role in the answer.
    context_preview = (context[:800] if context else "") if retrieval_used else ""

    # Build last-tool evidence line for the critic
    tool_evidence = ""
    if last_tool_name and last_tool_result is not None:
        result_str = str(last_tool_result)
        status = "FAILED" if result_str.startswith("Error:") else "SUCCEEDED"
        tool_evidence = f"Last Tool: {last_tool_name} → {status}\nResult snippet: {result_str[:300]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"User Question:\n{user_input}\n\n"
                f"Assistant Response:\n{response_preview}\n\n"
                f"Retrieval Used:\n{retrieval_used}\n\n"
                f"Context Matches:\n{match_count}\n\n"
                f"Retrieved Context:\n{context_preview}\n\n"
                f"{tool_evidence}"
            ),
        },
    ]

    try:
        # High determinism configuration (temp=0) with 32 token ceiling
        res = chat_ollama(
            messages,
            model=CRITIC_MODEL,
            num_predict=32,
            temperature=0
        )
        return res.strip()
    except Exception as e:
        return f"Error: Critic LLM failed - {str(e)}"