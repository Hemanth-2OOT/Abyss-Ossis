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

        # P3 fix: track written line count in memory so we only pay the
        # read+rewrite cost once every MAX_LOG_LINES writes, not every write.
        self._log_line_count = 0

    def log(self, text):
        MAX_LOG_LINES = 500

        # Fast path: append-only. No read required.
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        self._log_line_count += 1

        # Slow path: trim only when we've written 2x the limit since last trim.
        if self._log_line_count >= MAX_LOG_LINES:
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                if len(lines) > MAX_LOG_LINES:
                    with open(self.log_path, "w", encoding="utf-8") as f:
                        f.writelines(lines[-MAX_LOG_LINES:])
            except OSError:
                pass
            self._log_line_count = 0

