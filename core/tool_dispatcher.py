import subprocess
from rich.console import Console

from core.fsm_tracker import FSMTracker
from tools.directory_reader import list_files
from tools.file_reader import read_file
from tools.file_writer import write_file
from tools.index_storage import search_index
from tools.index_storage import update_file_index

console = Console()

def normalize_path(path: str) -> str:
    if not path:
        return ""
    import os
    return os.path.normpath(path).replace('\\', '/')

class ToolDispatcher:
    def __init__(self, session):
        self.session = session
        
    def _try_auto_install(self, cmd: str, result: dict) -> dict:
        # A mock representation of the original _try_auto_install
        # If the original one in cli.py is needed, it could be moved here.
        # For this refactor, we will import it from cli or move it to tool_dispatcher.
        # Since it relies on cli state, we can pass it as a callback or move it.
        pass

    def execute(self, tool_name: str, tool_args: dict, fsm: FSMTracker, opened_files_cache: dict, written_files: set, auto_install_callback=None) -> dict:
        """
        Executes a tool and returns the tool result.
        Also updates the opened_files_cache, written_files, and fsm state if necessary.
        """
        # Prerequisite validation is handled by fsm.can_transition() before execution
        
        tool_result = None
        try:
            if tool_name == "list_files":
                tool_result = list_files()
            elif tool_name == "read_file":
                f_path = tool_args.get("path")
                tool_result = read_file(f_path)
                if not str(tool_result).startswith("Error:"):
                    opened_files_cache[normalize_path(f_path)] = str(tool_result)
            elif tool_name == "write_file":
                p = normalize_path(tool_args.get("path"))
                c = tool_args.get("content", "")
                tool_result = write_file(p, c)
                if not str(tool_result).startswith("Error:"):
                    written_files.add(p)
                    opened_files_cache[p] = c
                    try:
                        update_file_index(self.session, p)
                    except Exception:
                        pass
            elif tool_name == "search_index":
                tool_result = search_index(self.session, tool_args.get("query"))
            elif tool_name == "run_command":
                cmd = tool_args.get("command")
                if "rm " in cmd or "deltree" in cmd:
                    tool_result = {
                        "success": False, "stdout": "",
                        "stderr": "Error: Destructive shell operations forbidden."
                    }
                else:
                    console.print(f"[dim]Executing: {cmd}[/dim]")
                    from core.resource_monitor import watchdog
                    import time
                    
                    watchdog.check()
                    
                    p_res = subprocess.Popen(
                        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )
                    
                    start_t = time.time()
                    while p_res.poll() is None:
                        if time.time() - start_t > 45:
                            p_res.kill()
                            raise TimeoutError("Command timed out after 45s.")
                        
                        watchdog.check()
                        time.sleep(0.5)
                        
                    stdout, stderr = p_res.communicate()
                    tool_result = {
                        "success": p_res.returncode == 0,
                        "stdout": stdout,
                        "stderr": stderr
                    }
                    if auto_install_callback:
                        tool_result = auto_install_callback(cmd, tool_result)
            else:
                tool_result = f"Error: Unknown tool '{tool_name}'."
        except Exception as ex:
            tool_result = f"Error executing tool: {str(ex)}"
            
        fsm.mark_event(tool_name, not str(tool_result).startswith("Error:"))
        return tool_result
