import os
from core.sandbox import sandbox
from core.logger import get_logger

logger = get_logger(__name__)

DEFAULT_ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".java", ".cpp", ".c", ".h", 
    ".go", ".rs", ".cs", ".md", ".json", ".yaml", ".yml", ".html", ".css"
}

def list_files(path=".", extensions=None):
    """
    Recursively lists files in the safe path.
    
    Configuration Contract:
    - extensions=None: Filters using standard DEFAULT_ALLOWED_EXTENSIONS.
    - extensions=[]: Disables filtering entirely (returns all files).
    - extensions=[...]: Filters using specific custom extensions provided.
    """
    try:
        safe_path = sandbox.get_safe_path(path)
        files = []
        
        # 1. Explicitly document intent instead of relying on Python truthiness
        if extensions is None:
            allowed = DEFAULT_ALLOWED_EXTENSIONS
        elif isinstance(extensions, list) and len(extensions) == 0:
            allowed = None  # Explicitly None means "allow everything"
        else:
            allowed = set(extensions)

        for root, dirs, filenames in os.walk(safe_path):
            dirs[:] = [
                d for d in dirs 
                if d not in {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea", ".vscode", "build", "dist"}
            ]

            for filename in filenames:
                if allowed is not None:
                    _, ext = os.path.splitext(filename)
                    if ext.lower() not in allowed:
                        continue
                
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, safe_path)
                files.append(rel_path.replace("\\", "/"))

        return "\n".join(sorted(files))
    except Exception as e:
        logger.error(f"Failed to list directory {path}: {e}")
        return f"Error: {e}"