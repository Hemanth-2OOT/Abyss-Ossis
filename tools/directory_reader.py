import os
from core.sandbox import sandbox
from core.logger import get_logger

logger = get_logger(__name__)

def list_files(path="."):
    try:
        safe_path = sandbox.get_safe_path(path)
        return "\n".join(os.listdir(safe_path))
    except Exception as e:
        logger.error(f"Failed to list directory {path}: {e}")
        return f"Error: {e}"