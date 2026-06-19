import os
import sys
from core.logger import get_logger

logger = get_logger(__name__)

def read_file(path):
    """
    Reads a file directly from the file system using sandbox safe path.
    Returns content wrapped in Markdown code blocks.
    """
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        from core.sandbox import sandbox

        safe_path = sandbox.get_safe_path(path)

        if not os.path.exists(safe_path):
            return f"Error: File '{path}' does not exist on disk."

        if os.path.isdir(safe_path):
            return f"Error: '{path}' is a directory, not a file."

        _, ext = os.path.splitext(safe_path)
        lang = ext.lstrip('.') if ext else ""

        with open(safe_path, "r", encoding="utf-8") as f:
            content = f.read()

        return (
            f"--- START OF FILE: {path} ---\n"
            f"```{lang}\n"
            f"{content}\n"
            f"```\n"
            f"--- END OF FILE: {path} ---"
        )

    except Exception as e:
        logger.exception("Failed to read file")
        return f"Error reading file: {str(e)}"