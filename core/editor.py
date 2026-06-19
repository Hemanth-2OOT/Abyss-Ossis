from tools.file_reader import read_file


def build_edit_prompt(path, instruction):
    content = read_file(path)

    prompt = f"""
FILE:
{path}

CODE:
{content}

TASK:
{instruction}

Return FULL updated file only.
"""
    return prompt