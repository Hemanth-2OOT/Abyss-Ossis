import difflib

def show_diff(old_code, new_code):
    diff = difflib.unified_diff(
        old_code.splitlines(),
        new_code.splitlines(),
        fromfile="OLD",
        tofile="NEW",
        lineterm=""
    )

    colored = []

    for line in diff:
        # Green for added lines, excluding header lines
        if line.startswith("+") and not line.startswith("+++"):
            colored.append(f"[green]{line}[/green]")
        # Red for removed lines, excluding header lines
        elif line.startswith("-") and not line.startswith("---"):
            colored.append(f"[red]{line}[/red]")
        # Neutral for context lines
        else:
            colored.append(line)

    return "\n".join(colored)