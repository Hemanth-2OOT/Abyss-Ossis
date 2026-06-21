import json

def _find_json_end(text, start):
    """Return index of the closing '}' that matches text[start]=='{', or -1."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
    return -1


def extract_json(text):
    """
    Safely extracts and parses JSON from LLM outputs, bypassing
    surrounding markdown fences or prose block content.
    B7 fix: uses depth-tracking instead of rfind('}') to find the correct
    closing brace, preventing mis-parse when prose after the JSON contains '}'.
    """
    text = text.strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("Failed to extract valid JSON")

    end = _find_json_end(text, start)
    if end == -1:
        raise ValueError("Failed to extract valid JSON")

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to extract valid JSON: {exc}") from exc