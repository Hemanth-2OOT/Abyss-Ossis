"""
context_builder.py

Builds a context block from retrieved index matches.
Enforces an adaptive character budget to avoid flooding small model context windows.

Budget hierarchy:
  1. AST matches (function/method/class) — highest priority, full source
  2. Semantic matches — include if budget allows
  3. File fallback entries — truncated snippets only
"""

DEFAULT_CONTEXT_CHARS = 2500
CODING_CONTEXT_CHARS = 8500

DEFAULT_MATCHES = 6
CODING_MATCHES = 14


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
        # Truncate very long function bodies dynamically based on context sizes
        if len(source) > 1500:
            source = source[:1500] + "\n... (truncated)"
        lines.append(f"Source:\n{source}")

    elif item_type == "class":
        lines.append(f"Class: {item.get('name', '')}")
        if item.get("docstring"):
            lines.append(f"Docstring: {item['docstring']}")
        methods = item.get("methods", [])
        if methods:
            lines.append(f"Methods: {', '.join(methods)}")
        source = item.get("source", "")
        if len(source) > 1200:
            source = source[:1200] + "\n... (truncated)"
        lines.append(f"Source:\n{source}")

    elif item_type == "call":
        lines.append(f"'{item.get('caller', '?')}' calls '{item.get('name', '?')}'")

    elif item_type == "import":
        lines.append(f"Imports '{item.get('name', '')}' from '{item.get('module', '')}'")

    elif item_type == "file":
        content = item.get("content", "")
        lines.append(f"Content snippet:\n{content[:600]}")

    else:
        lines.append(str(item))

    return "\n".join(lines)


def build_context(matches, task_type="general"):
    """
    Build an adaptive, budget-capped context string from a list of index matches.
    Returns empty string if no matches.
    """
    if not matches:
        return ""

    # Scale character and item quotas depending on task profiles
    if task_type in ("coding", "debugging"):
        max_context_chars = CODING_CONTEXT_CHARS
        max_matches = CODING_MATCHES
    else:
        max_context_chars = DEFAULT_CONTEXT_CHARS
        max_matches = DEFAULT_MATCHES

    # Stable weighted item ranking: Prioritize AST entities while preserving relevance scores
    scored_matches = []
    for item in matches:
        score = item.get("score", 0.0)
        if item.get("type") in ("function", "method", "class"):
            score += 2.0
        scored_matches.append((score, item))

    scored_matches.sort(key=lambda x: x[0], reverse=True)
    ordered = [x[1] for x in scored_matches]

    context_parts = []
    total_chars = 0
    rendered = 0

    for item in ordered:
        if rendered >= max_matches:
            break

        snippet = _render_match(item)
        snippet_len = len(snippet)

        if total_chars + snippet_len > max_context_chars:
            if item.get("type") == "file":
                remaining = max_context_chars - total_chars - 60
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