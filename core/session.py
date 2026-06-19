import os

class ProjectSession:
    def __init__(self, root_path):
        self.root = os.path.abspath(root_path)

        self.index_path = os.path.join(self.root, ".localagent.index.json")
        self.memory_path = os.path.join(self.root, ".localagent.memory.json")
        self.log_path = os.path.join(self.root, ".localagent.logs.txt")

        # Lock sandbox to this workspace
        from core.sandbox import sandbox
        sandbox.workspace_root = self.root

    def log(self, text):
        MAX_LOG_LINES = 500
        lines = []
        
        if os.path.exists(self.log_path):
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
        lines.append(text + "\n")
        
        if len(lines) > MAX_LOG_LINES:
            lines = lines[-MAX_LOG_LINES:]
            
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
