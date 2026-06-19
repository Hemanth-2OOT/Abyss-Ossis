from tools.file_reader import read_file

def build_edit_prompt(path, instruction):
    """
    Reads the target file and wraps it with the user's instructions
    so the worker knows exactly what to change.
    """
    content = read_file(path)
    
    return f"""
You are an expert code editor. 
Below is the current content of '{path}':

---
{content}
---

Instruction: 
{instruction}

Provide ONLY the final version of the code. 
Do not include any other text, explanations, or markdown formatting.
"""