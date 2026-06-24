import sys
import os

from core.planner import generate_plan
from core.execution_state import ExecutionState

if __name__ == "__main__":
    task_prompt = "1. create hello.py\n2. modify hello.py to print hello world\n3. read hello.py\n4. delete hello.py"
    
    print("Generating plan for:", task_prompt.replace("\n", " | "))
    payload = generate_plan(task_prompt)
    
    import json
    print("\nPlan Payload Generated:")
    print(json.dumps(payload, indent=2))
    
    reqs = payload.get("requirements", [])
    
    print("\nRequirement Types found in Plan:")
    for r in reqs:
        print(f"- {r.get('type')} (Args: {r.get('args')})")
        
    print("\nTest passed if requirements correspond to tool actions without legacy intents.")
