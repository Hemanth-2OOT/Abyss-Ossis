
from systems.ollama_client import chat_ollama
from config import PLANNER_MODEL
from tools.json_utils import extract_json

def generate_plan(user_input, context=None):
    """
    Decomposes an engineering task into an architectural plan containing
    explicit structural constraints and rule verification checkpoints.
    """
    system_prompt = """
You are an expert system architect and planner agent.
Your job is to break down complex code engineering tasks into highly precise implementation steps.
You must extract structural rules, state invariants, and boundary constraints to enforce logical runtime safety.

Return ONLY a valid JSON object with no markdown fences, prose, or outer wrappers:
{
  "steps": [
    "Step 1 implementation directive string",
    "Step 2 implementation directive string"
  ],
  "constraints": [
    "Invariant condition 1 (e.g., snake direction must not reverse instantly)",
    "Invariant condition 2 (e.g., coordinates must be validated within bounds before index modifications)"
  ],
  "edge_cases": [
    "Critical boundary or failure condition 1",
    "Critical boundary or failure condition 2"
  ]
}
"""
    
    if context:
        system_prompt += f"\nPROJECT CONTEXT EVIDENCE:\n{context}\n"
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    
    response = chat_ollama(
        messages,
        model=PLANNER_MODEL,
        temperature=0.2,
        num_predict=192
    )
    
    try:
        return extract_json(response)
    except Exception:
        # Secure structure fallback if parsing returns raw strings
        return {
            "steps": [response.strip()],
            "constraints": ["Maintain logical alignment with structural specifications."],
            "edge_cases": ["Handle empty inputs or data format anomalies."]
        }