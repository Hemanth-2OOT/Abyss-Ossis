import os
import sys
from core.tool_result import ToolResult
from core.logger import get_logger

logger = get_logger(__name__)

def read_file(path) -> ToolResult:
    """
    Reads a file directly from the file system using sandbox safe path.
    Returns RAW file content only — no markdown fences, no header/footer
    wrapper text. Callers that want a human-readable display (e.g. the
    /read CLI command) should add their own formatting on top of this.
    Internal tool consumers (replace_chunk, build_edit_prompt, etc.) need
    the literal file content to do exact substring matching and editing,
    so this function must never alter the bytes it read.
    """
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        from core.sandbox import sandbox

        safe_path = sandbox.get_safe_path(path)

        if not os.path.exists(safe_path):
            return ToolResult(success=False, stdout="", stderr=f"Error: File '{path}' does not exist on disk.")

        if os.path.isdir(safe_path):
            return ToolResult(success=False, stdout="", stderr=f"Error: '{path}' is a directory, not a file.")

        # Prevent massive memory consumption/OOM on huge files (limit: 2MB)
        try:
            if os.path.getsize(safe_path) > 2 * 1024 * 1024:
                return ToolResult(success=False, stdout="", stderr=f"Error: File '{path}' exceeds the 2MB read limit.")
        except OSError as e:
            return ToolResult(success=False, stdout="", stderr=f"Error: Cannot access file '{path}': {e}")

        with open(safe_path, "r", encoding="utf-8") as f:
            content = f.read()

        return ToolResult(
            success=True,
            stdout=content,
            summary=f"Read {len(content)} bytes from {path}."
        )

    except Exception as e:
        logger.exception("Failed to read file")
        return ToolResult(success=False, stdout="", stderr=f"Error reading file: {str(e)}")