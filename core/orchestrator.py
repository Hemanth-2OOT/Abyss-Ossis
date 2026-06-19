import json
import re
from systems.ollama_client import chat_ollama


def extract_json(text):
    text = text.strip()
    
    # Fast path: pure JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Find the first { and the last }
    start = text.find("{")
    end = text.rfind("}")
    
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
            
    raise ValueError("Failed to extract valid JSON")


def classify_task(user_input):
    system_prompt = """
You are an orchestration agent.

Classify the user request.

Task types:
- coding
- debugging
- explanation
- lookup
- chat
- file_analysis

Return ONLY JSON.

Example:
{
  "task_type": "coding",
  "needs_planner": true,
  "needs_tools": true,
  "needs_retrieval": false
}
Example 2:
{
  "task_type": "lookup",
  "needs_planner": false,
  "needs_tools": false,
  "needs_retrieval": true
}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    response = chat_ollama(messages)

    try:
        return extract_json(response)
    except Exception:
        return {
            "task_type": "chat",
            "needs_planner": False,
            "needs_tools": False,
            "needs_retrieval": False
        }