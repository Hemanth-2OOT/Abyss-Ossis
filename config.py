OLLAMA_URL = "http://localhost:11434/api/generate"

# Role-Based Model Infrastructure
PLANNER_MODEL = "qwen2.5-coder:7b"
WORKER_MODEL = "qwen2.5-coder:7b"
CRITIC_MODEL = "qwen2.5-coder:7b"
EDITOR_MODEL = "qwen2.5-coder:7b"
DEFAULT_MODEL = "qwen2.5-coder:7b"

TEMPERATURE = 0.3
MAX_CONTEXT = 4096

# Memory Safety Configuration
WARNING_RAM_PERCENT = 85.0
MAX_RAM_PERCENT = 90.0
MIN_AVAILABLE_VRAM_MB = 512
MODEL_MEMORY_REQUIREMENTS = {
    "qwen2.5-coder:7b": 2.0,
    "qwen3:8b": 3.0,
    "deepseek-coder:6.7b": 2.5,
    "nomic-embed-text:latest": 0.5,
    "mannix/llama3.1-8b-abliterated:latest": 3.0
}

MEMORY_PATH = "data/memory.json"
WHITELIST_DIRS = []