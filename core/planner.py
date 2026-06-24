from systems.ollama_client import chat_ollama
from config import PLANNER_MODEL
from tools.json_utils import extract_json
from core.tool_registry import VALID_TOOLS, TOOL_REGISTRY

PLANNER_TOOLS_STR = "\n".join(
    f"- {name}: {TOOL_REGISTRY[name].description} (Requires: {', '.join(TOOL_REGISTRY[name].required_args) if TOOL_REGISTRY[name].required_args else 'None'})"
    for name in VALID_TOOLS
)

AGENT_CAPABILITIES = {
    "tools": VALID_TOOLS,
    "can_create_files": True,
    "can_execute": True,
    "can_delete": True,
    "can_access_network": False
}

def generate_plan(user_input, context=None, max_retries=3):
    """
    Generates a task-oriented plan.
    """
    
    context_str = f"Context:\n{context}\n\n" if context else ""
    
    system_prompt = f"""You are an expert AI Planner orchestrating an autonomous coding agent.
Your job is to break down the user's request into a strict sequence of tool-based requirements.

{context_str}User Request: {user_input}

Agent Capabilities:
{AGENT_CAPABILITIES}

Available tools for planning:
{PLANNER_TOOLS_STR}

Output ONLY valid JSON matching this schema:
{{
  "steps": [
    "Step 1 implementation directive string"
  ],
  "requirements": [
    {{"id": "R1", "type": "search_index", "args": {{}}, "metadata": {{"purpose": "<Describe what needs to be found>"}}}},
    {{"id": "R2", "type": "write_file", "args": {{"path": "<actual_target_filename_here>"}}, "depends_on": ["R1"]}},
    {{"id": "R3", "type": "replace_chunk", "args": {{"path": "<actual_target_filename_here>"}}, "metadata": {{"context": ["<insert_source_file>"]}}, "depends_on": ["R2"]}}
  ],
  "constraints": [
    "Invariant condition 1"
  ]
}}

CRITICAL RULES:
1. DO NOT copy the example output above. You must generate a plan strictly for the USER's specific request.
2. If you do not know the target file and the user didn't specify one, emit search_index or list_files.
3. DO NOT write actual source code in the plan. DO NOT include "content" or "code" fields in your requirements. The plan must only contain file names and tool requirements. The worker agent will write the actual code later.
4. Ensure requirements properly use "depends_on" to form a valid execution sequence.
"""
    
    if context:
        system_prompt += f"\nPROJECT CONTEXT EVIDENCE:\n{context}\n"
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    
    for attempt in range(max_retries):
        response = chat_ollama(
            messages,
            model=PLANNER_MODEL,
            temperature=0.2,
            num_predict=1024
        )
        
        try:
            payload = extract_json(response)
            from core.tool_registry import PlannerContractError
            
            reqs = payload.get("requirements", [])
            if not reqs:
                raise PlannerContractError("No requirements generated.")
                
            for r in reqs:
                rt = str(r.get("type", "")).lower()
                r["type"] = rt
                
                if rt not in VALID_TOOLS:
                    raise PlannerContractError(f"Planner generated unknown requirement type: {rt}")
                    
                tool_spec = TOOL_REGISTRY[rt]
                args = r.get("args", {})
                if not isinstance(args, dict):
                    raise PlannerContractError(f"Requirement {rt} 'args' must be an object.")
                    
                for req_arg in tool_spec.required_args:
                    if req_arg not in args or not str(args[req_arg]).strip() or str(args[req_arg]).lower() in ("???", "unknown", "none", "null"):
                        raise PlannerContractError(f"Requirement {rt} is missing required arg '{req_arg}'.")
                        
                if tool_spec.argument_validator:
                    tool_spec.argument_validator(args)
                    
            return payload
            
        except PlannerContractError as e:
            from rich.console import Console
            Console().print(f"[yellow]PlannerContractError (attempt {attempt+1}): {str(e)} Regenerating plan...[/yellow]")
            continue
        except Exception as e:
            from rich.console import Console
            Console().print(f"[yellow]JSON Parse Error (attempt {attempt+1}): {str(e)}[/yellow]")
            continue
            
    # Secure structure fallback if parsing fails validations
    return {
            "steps": ["Plan generation failed. Worker must proceed autonomously based on the user's original request."],
            "requirements": [],
            "constraints": [],
            "edge_cases": []
        }