import os
from config import WHITELIST_DIRS

class SandboxException(Exception):
    pass

class WorkspaceSandbox:
    def __init__(self, workspace_root=".", whitelist_dirs=None):
        self.workspace_root = os.path.abspath(os.path.realpath(workspace_root))
        # Use config if none provided
        if whitelist_dirs is None:
            whitelist_dirs = list(WHITELIST_DIRS) if WHITELIST_DIRS else []
            
        self.whitelist_dirs = [
            os.path.abspath(os.path.realpath(d)) for d in whitelist_dirs
        ]

    def get_safe_path(self, path):
        abs_path = os.path.abspath(os.path.realpath(path))
        # Check against workspace root
        try:
            if os.path.commonpath([abs_path, self.workspace_root]) == self.workspace_root:
                return abs_path
        except ValueError:
            pass
            
        # Check against whitelist
        for w_dir in self.whitelist_dirs:
            if w_dir:
                try:
                    if os.path.commonpath([abs_path, w_dir]) == w_dir:
                        return abs_path
                except ValueError:
                    pass
                
        raise SandboxException(f"Access denied: Path '{path}' is outside the allowed workspace.")

sandbox = WorkspaceSandbox(whitelist_dirs=WHITELIST_DIRS)