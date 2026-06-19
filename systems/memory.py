import json
import os
from core.logger import get_logger

logger = get_logger(__name__)

def load_memory(session):
    if not os.path.exists(session.memory_path):
        return {}

    try:
        with open(session.memory_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

            if not content:
                return {}

            return json.loads(content)

    except Exception as e:
        logger.error(f"Memory load error: {e}", exc_info=True)
        return {}


def save_memory(session, memory):
    os.makedirs(os.path.dirname(session.memory_path), exist_ok=True)
    
    # Garbage-proof memory cap (max 50 entries)
    MAX_MEMORY = 50
    if len(memory) > MAX_MEMORY:
        memory = dict(list(memory.items())[-MAX_MEMORY:])
        
    with open(session.memory_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)


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


def recall(session, key):
    memory = load_memory(session)
    return memory.get(key)