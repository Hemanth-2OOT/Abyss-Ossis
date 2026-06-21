import os
import ast
import shutil
from core.sandbox import sandbox
from core.logger import get_logger

logger = get_logger(__name__)

def write_file(path, content):
    if not content.strip():
        return "Error: Refusing to write empty content."
            
    try:
        safe_path = sandbox.get_safe_path(path)
        
        # Create parent directories automatically
        parent_dir = os.path.dirname(safe_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        backup_path = safe_path + ".bak"
                
        if os.path.exists(safe_path):
            shutil.copy2(safe_path, backup_path)
                    
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
                    
        if safe_path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                if os.path.exists(backup_path):
                    shutil.move(backup_path, safe_path)
                else:
                    os.remove(safe_path)
                return f"Error: Write aborted due to SyntaxError: {e}. Backup restored."
                        
        if os.path.exists(backup_path):
            os.remove(backup_path)
                    
        # NOTE: Indexing is handled by the caller (cli.py), which has access
        # to the session object that update_file_index requires. write_file()
        # itself has no session, so it cannot safely call update_file_index.
                
        return "File updated successfully."
    except Exception as e:
        print("WRITE_FILE ERROR:", repr(e))
        logger.error(f"Failed to write file {path}: {e}")
        return f"Error: {e}"