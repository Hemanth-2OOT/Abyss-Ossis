import json
from systems.ollama_client import chat_ollama
from config import PLANNER_MODEL

def extract_json(text):
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break  # Fallback to next '{' if the balanced block isn't valid JSON
        start = text.find("{", start + 1)
            
    raise ValueError("Failed to extract valid JSON")


def complexity_score(prompt):
    """
    Evaluates the algorithmic and architectural overhead of a prompt to determine
    the appropriate depth of execution.
    """
    score = 0
    p = prompt.lower()

    if len(prompt) > 200:
        score += 2
    if "game" in p or "simulation" in p or "physics" in p:
        score += 2
    if "api" in p or "route" in p or "endpoint" in p or "server" in p:
        score += 2
    if "bug" in p or "fix" in p or "error" in p or "traceback" in p:
        score += 3
    if "multiple files" in p or "refactor" in p or "restructure" in p:
        score += 3

    return score


def classify_task_llm(user_input):
    """
    Fallback LLM classifier used only if quick-rule keyword heuristics are completely ambiguous.
    """
    system_prompt = """
You are an orchestration router agent.
Analyze the user's request and classify it into one of these types:
- coding, debugging, explanation, lookup, chat, file_analysis, execute

Output strictly in JSON format with no markdown wrappers:
{
  "task_type": "coding" | "debugging" | "explanation" | "lookup" | "chat" | "file_analysis" | "execute",
  "needs_planner": true | false,
  "needs_tools": true | false,
  "needs_retrieval": true | false
}
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    try:
        response = chat_ollama(messages, model=PLANNER_MODEL, temperature=0.1, num_predict=128)
        return extract_json(response)
    except Exception as e:
        from core.resource_monitor import ResourceSafetyError
        if isinstance(e, ResourceSafetyError):
            raise
        return {
            "task_type": "coding",
            "needs_planner": True,
            "needs_tools": True,
            "needs_retrieval": False
        }


def classify_task(user_input):
    """
    Fast-path heuristic task router. Bypasses the LLM classification entirely for 80%
    of requests to eradicate the 3-6s startup lag and assigns an adaptive capability profile.
    """
    text = user_input.lower()
    score = complexity_score(user_input)

    coding_words = ["build", "create", "write", "make", "implement", "code", "generate",
                    "improve", "update", "edit", "enhance", "redesign", "rewrite",
                    "change", "add", "modify", "extend", "upgrade",
                    "delete", "remove", "rename", "move"]
    debug_words = ["bug", "fix", "error", "traceback", "failing", "crash", "broken"]
    analysis_words = ["architecture", "layout", "structure", "explain how", "fit together"]

    # Rule 1: High certainty debugging
    if any(w in text for w in debug_words):
        task = {
            "task_type": "debugging",
            "needs_planner": score >= 2,
            "needs_tools": True,
            "needs_retrieval": True
        }
    # Rule 2: High certainty coding
    elif any(w in text for w in coding_words):
        task = {
            "task_type": "coding",
            "needs_planner": True,
            "needs_tools": True,
            "needs_retrieval": False
        }
    # Rule 3: Project Architecture / Structural Investigation
    elif any(w in text for w in analysis_words):
        task = {
            "task_type": "file_analysis",
            "needs_planner": False,
            "needs_tools": True,
            "needs_retrieval": True
        }
    # Rule 4: File inspection and commands
    elif any(w in text for w in ["list files", "read files", "show directory", "open file", "ls", "cat"]):
        task = {
            "task_type": "file_analysis",
            "needs_planner": False,
            "needs_tools": True,
            "needs_retrieval": False
        }
    # Rule 5: Execution commands
    elif any(w in text for w in ["run", "execute", "start", "launch", "serve", "test"]):
        task = {
            "task_type": "execute",
            "needs_planner": False,
            "needs_tools": True,
            "needs_retrieval": False
        }
    # Fallback to LLM classifier if words are completely ambiguous
    else:
        task = classify_task_llm(user_input)

    # Attach dynamic cognitive constraints based on complexity score
    task["complexity_score"] = score
    task["needs_critic"] = score >= 5
    
    return task