import json
from systems.ollama_client import chat_ollama

def generate_plan(user_input, context=None):
    system_prompt = """
You are a planner agent.
Your job is to break down complex tasks into a step-by-step plan.
Return ONLY a JSON list of strings.

Example:
[
  "Create file systems/memory.py",
  "Modify cli.py to add memory commands",
  "Update worker.py to inject memory"
]
"""
    
    if context:
        system_prompt += f"\nPROJECT CONTEXT:\n{context}\n"
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    
    response = chat_ollama(messages)
    
    # Try to parse JSON
    text = response.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [response]
