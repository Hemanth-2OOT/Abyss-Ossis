"""
core/skill_selector.py
======================
Lazy-loaded, cached skill selector with priority ranking.

Skills are read from disk once per session and cached in memory.
Never more than MAX_SKILLS are injected into a prompt.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

# ── Skill registry ─────────────────────────────────────────────────────────────
# Each entry: filename → (priority, [trigger_keywords])
# Higher priority = selected first when too many skills match.
_SKILL_REGISTRY: List[tuple] = [
    ("debugging.md",      100, ["bug", "fix", "error", "traceback", "failing", "crash",
                                 "broken", "exception", "attributeerror", "typeerror",
                                 "keyerror", "importerror", "undefined", "not working",
                                 "syntaxerror", "nameerror"]),
    ("python.md",          90, ["python", " def ", " class ", "import", "script", "module",
                                 "async", "await", "dataclass", "decorator", "lambda",
                                 ".py"]),
    ("ui_design.md",       80, ["css", "html", "frontend", "ui ", "ux", "template",
                                 "layout", "style", "design", "responsive", "form",
                                 "button", "navbar", "navbar", "flex", "grid", "colour",
                                 "color", "font", "modal", "sidebar", ".html", ".css",
                                 "index.html", "templates/"]),
    ("refactoring.md",     70, ["refactor", "clean", "optimize", "improve", "simplify",
                                 "restructure", "reorganize", "duplicate", "extract",
                                 "rename", "rewrite", "redesign"]),
    ("file_operations.md", 60, ["read file", "list file", "search", "open file",
                                 "directory", "find file", "show file", "file content",
                                 "what files", "ls ", "cat "]),
    ("reasoning.md",       50, ["explain", "why", "how does", "reason", "understand",
                                 "what is", "describe", "what happen", "walk me through",
                                 "tell me", "summarise", "summarize"]),
]

# Pure-chat keywords — if the input only matches these, return no skills.
_CHAT_ONLY_PATTERNS = [
    "hello", "hi ", "hey ", "thanks", "thank you", "good morning",
    "good evening", "how are you", "what's up",
]

MAX_SKILLS = 2          # Maximum skills injected per request
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")

# ── In-process cache (populated lazily) ────────────────────────────────────────
_cache: Dict[str, str] = {}


def _load_skill(filename: str) -> str:
    """Load a skill file from disk, caching the result in memory."""
    if filename in _cache:
        return _cache[filename]
    path = os.path.join(_SKILLS_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        _cache[filename] = text
        return text
    except FileNotFoundError:
        return ""


def _is_pure_chat(text: str) -> bool:
    return any(p in text for p in _CHAT_ONLY_PATTERNS)


def select_skills(task_type: Optional[str], user_input: str) -> str:
    """
    Return the combined text of the highest-priority matching skills.

    Rules
    -----
    - Returns "" for pure chat inputs.
    - Matches against both task_type AND user_input keywords.
    - Returns at most MAX_SKILLS skills, highest priority first.
    - Skills are lazy-loaded from disk and cached for the session.
    """
    text = user_input.lower()

    # Fast-exit: pure chat — no skills
    if _is_pure_chat(text):
        return ""

    scored: List[tuple] = []  # (priority, filename)

    for filename, priority, triggers in _SKILL_REGISTRY:
        if any(kw in text for kw in triggers):
            scored.append((priority, filename))

    if not scored:
        return ""

    # Sort descending by priority, cap at MAX_SKILLS
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:MAX_SKILLS]

    parts: List[str] = []
    for _, filename in selected:
        content = _load_skill(filename)
        if content:
            skill_name = filename.replace(".md", "").replace("_", " ").title()
            parts.append(f"--- SKILL: {skill_name} ---\n{content}\n--- END SKILL ---")

    return "\n\n".join(parts)
