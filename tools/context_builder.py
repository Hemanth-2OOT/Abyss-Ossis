"""
context_builder.py

Builds a context block from retrieved index matches.
Enforces a strict character budget to avoid flooding small model context windows.

Budget hierarchy:
  1. AST matches (function/method/class) — highest priority, full source
  2. Semantic matches — include if budget allows
  3. File fallback entries — truncated snippets only
"""

# ~2500 chars ≈ ~600 tokens, leaving room for system prompt + user message
MAX_CONTEXT_CHARS = 2500
# Max number of total matches rendered, regardless of budget
MAX_MATCHES = 6


def _render_match(item):
    """Render a single index match into a human-readable snippet string."""
    item_type = item.get("type", "unknown")
    file_path = item.get("file", "unknown")
    lines = [f"--- [{item_type.upper()}] {file_path} ---"]

    if item_type in ("function", "method"):
        lines.append(f"Name: {item.get('name', '')}")
        if item.get("docstring"):
            lines.append(f"Docstring: {item['docstring']}")
        source = item.get("source", "")
        # Truncate very long function bodies
        if len(source) > 800:
            source = source[:800] + "\n... (truncated)"
        lines.append(f"Source:\n{source}")

    elif item_type == "class":
        lines.append(f"Class: {item.get('name', '')}")
        if item.get("docstring"):
            lines.append(f"Docstring: {item['docstring']}")
        methods = item.get("methods", [])
        if methods:
            lines.append(f"Methods: {', '.join(methods)}")
        source = item.get("source", "")
        if len(source) > 600:
            source = source[:600] + "\n... (truncated)"
        lines.append(f"Source:\n{source}")

    elif item_type == "call":
        lines.append(f"'{item.get('caller', '?')}' calls '{item.get('name', '?')}'")

    elif item_type == "import":
        lines.append(f"Imports '{item.get('name', '')}' from '{item.get('module', '')}'")

    elif item_type == "file":
        content = item.get("content", "")
        # File fallbacks get very short snippets
        lines.append(f"Content snippet:\n{content[:400]}")

    else:
        lines.append(str(item))

    return "\n".join(lines)


def build_context(matches):
    """
    Build a budget-capped context string from a list of index matches.
    Returns empty string if no matches.
    """
    if not matches:
        return ""

    # Partition matches by priority tier
    ast_matches = [m for m in matches if m.get("type") in ("function", "method", "class")]
    other_matches = [m for m in matches if m.get("type") not in ("function", "method", "class", "file")]
    file_matches = [m for m in matches if m.get("type") == "file"]

    ordered = ast_matches + other_matches + file_matches

    context_parts = []
    total_chars = 0
    rendered = 0

    for item in ordered:
        if rendered >= MAX_MATCHES:
            break

        snippet = _render_match(item)
        snippet_len = len(snippet)

        if total_chars + snippet_len > MAX_CONTEXT_CHARS:
            # Try to fit a truncated version for file fallbacks
            if item.get("type") == "file":
                remaining = MAX_CONTEXT_CHARS - total_chars - 60
                if remaining > 100:
                    short = _render_match({**item, "content": item.get("content", "")[:remaining]})
                    context_parts.append(short)
                    total_chars += len(short)
            break

        context_parts.append(snippet)
        total_chars += snippet_len
        rendered += 1

    if not context_parts:
        return ""

    header = f"[Context: {rendered} match(es), {total_chars} chars]\n"
    return header + "\n\n".join(context_parts)