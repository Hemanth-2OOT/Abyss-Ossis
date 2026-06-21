import difflib

def show_diff(old_code, new_code):
    """
    Returns a list of (line, style) tuples for safe rendering.
    style is one of "green", "red", or None (neutral/context line).
    Callers should print each line using Rich's `style=` parameter
    with markup=False, since diff lines are raw source code and may
    contain literal '[' or ']' characters that would break markup parsing.
    """
    diff = difflib.unified_diff(
        old_code.splitlines(),
        new_code.splitlines(),
        fromfile="OLD",
        tofile="NEW",
        lineterm=""
    )

    result = []

    for line in diff:
        # Green for added lines, excluding header lines
        if line.startswith("+") and not line.startswith("+++"):
            result.append((line, "green"))
        # Red for removed lines, excluding header lines
        elif line.startswith("-") and not line.startswith("---"):
            result.append((line, "red"))
        # Neutral for context lines
        else:
            result.append((line, None))

    return result