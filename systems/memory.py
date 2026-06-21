import json
import os
from core.logger import get_logger

logger = get_logger(__name__)

# ── Memory cache (P2 fix) ────────────────────────────────────────────────────
# get_memory() is called inside run_worker() on every LLM call in the inner
# tool loop (up to 12 times per turn). Cache keyed on mtime so writes via
# remember()/forget() are always reflected on the next read.
_memory_cache: dict = {}   # {memory_path: (mtime, data)}

def load_memory(session):
    path = session.memory_path
    if not os.path.exists(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _memory_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        data = json.loads(content) if content else {}
    except Exception as e:
        logger.error(f"Memory load error: {e}", exc_info=True)
        # Prevent silent overwrite of corrupted memory file
        if os.path.exists(path):
            import shutil
            shutil.move(path, path + ".corrupted.bak")
        raise RuntimeError(f"Memory file corrupted and backed up. Error: {e}")
    _memory_cache[path] = (mtime, data)
    return data


def save_memory(session, memory):
    os.makedirs(os.path.dirname(session.memory_path), exist_ok=True)

    # Garbage-proof memory cap (max 50 entries)
    MAX_MEMORY = 50
    if len(memory) > MAX_MEMORY:
        memory = dict(list(memory.items())[-MAX_MEMORY:])

    with open(session.memory_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
    # Invalidate cache so next load_memory reads the freshly written file.
    _memory_cache.pop(session.memory_path, None)


def remember(session, key, value):
    memory = load_memory(session)
    memory[key] = value
    save_memory(session, memory)


def forget(session, key):
    memory = load_memory(session)
    if key in memory:
        del memory[key]
        save_memory(session, memory)
        return True
    return False


def get_memory(session):
    return load_memory(session)