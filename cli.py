import os
import re
import sys
import time
import json
import hashlib
import subprocess
from threading import Thread
from queue import Queue, Empty
from collections import defaultdict
import config
from config import DEFAULT_MODEL

from rich.console import Console
from core.logger import get_logger
from systems.state import AgentState
from core.orchestrator import classify_task
from core.worker import run_worker
from core.metrics import MetricsTracker
from core.tool_dispatcher import ToolDispatcher
from core.resource_monitor import ResourceSafetyError, watchdog
from core.critic import critique_response
from core.guards import requires_more_info
from core.skill_selector import select_skills
from core.open_spec import build_open_spec
from core.post_tool_validator import validate_post_tool
from core.execution_state import ExecutionState, ToolEvent
from core.tool_result import ToolResult

from tools.file_reader import read_file
from tools.file_writer import write_file
from tools.directory_reader import list_files
from tools.replace_chunk import replace_chunk
from tools.run_command import run_command
from core.tool_router import detect_tool
from tools.code_indexer import build_index
from tools.index_storage import save_index, load_index, search_index, update_file_index
from tools.context_builder import build_context
from tools.edit_utils import build_edit_prompt
from tools.diff_viewer import show_diff
from systems.semantic_index import sync_faiss_with_ast
from core.session import ProjectSession

console = Console()
state = AgentState()
logger = get_logger("cli")
metrics = MetricsTracker()

PKG_ALIASES = {
    "PIL":     "Pillow",
    "cv2":     "opencv-python",
    "sklearn": "scikit-learn",
    "bs4":     "beautifulsoup4",
    "yaml":    "pyyaml",
    "dotenv":  "python-dotenv",
    "serial":  "pyserial",
    "usb":     "pyusb",
}

TOOL_ALIASES = {
    "file_read": "read_file",
    "read": "read_file",
    "cat": "read_file",
    "open_file": "read_file",
    "file_list": "list_files",
    "ls": "list_files",
    "grep": "search_files",
}

_PIP_COMMAND_PATTERN = re.compile(r"^\s*pip\s+install", re.IGNORECASE)

# Global session loops and installation limits
INSTALL_ATTEMPTS = defaultdict(int)
MAX_INSTALL_ATTEMPTS = 1

def _pip_name(import_name):
    return PKG_ALIASES.get(import_name, import_name)


def normalize_path(path_str: str) -> str:
    """Forces completely identical OS-agnostic lowercased path normalization across both sides."""
    if not path_str:
        return ""
    norm = os.path.normpath(path_str.strip()).lower()
    norm = norm.replace("\\", "/")
    norm = norm.lstrip("./").lstrip("/")
    return norm


def _try_auto_install(cmd, tool_result_dict):
    """Offers pip install when a run_command result contains ModuleNotFoundError."""
    stdout = tool_result_dict.get("stdout", "")
    stderr = tool_result_dict.get("stderr", "")
    combined_output = f"{stdout}\n{stderr}"

    if _PIP_COMMAND_PATTERN.match(cmd or ""):
        return tool_result_dict

    match = re.search(r"No module named '([^']+)'", combined_output)
    if not match:
        return tool_result_dict

    import_name = match.group(1).split(".")[0]
    pkg = _pip_name(import_name)

    if INSTALL_ATTEMPTS[pkg] >= MAX_INSTALL_ATTEMPTS:
        tool_result_dict["success"] = False
        tool_result_dict["stderr"] += f"\nINSTALL LOCKOUT: Further installation attempts for '{pkg}' are forbidden."
        return tool_result_dict

    console.print(f"[yellow]Missing package: '{import_name}' → pip install {pkg}[/yellow]")
    confirm = input(f"Run 'pip install {pkg}'? (y/n): ").lower()
    if confirm != "y":
        tool_result_dict["success"] = False
        tool_result_dict["stderr"] += f"\n\n[User declined install of '{pkg}']"
        return tool_result_dict

    INSTALL_ATTEMPTS[pkg] += 1

    proc = subprocess.run(
        ["pip", "install", "--only-binary", ":all:", pkg],
        capture_output=True, text=True
    )
    if proc.returncode == 0:
        out = (proc.stdout or "").strip()[-300:]
        console.print(f"[green]pip install {pkg} succeeded (binary wheel).[/green]")
        tool_result_dict["success"] = True
        tool_result_dict["stdout"] += (
            f"\n\n[Auto-install '{pkg}' OK]\n{out}\n"
            f"AUTO INSTALL SUCCESSFUL: {pkg}\n"
            f"CRITICAL INSTRUCTION: DO NOT RUN PIP INSTALL AGAIN.\n"
            f"The package '{pkg}' is now fully available. Immediately retry the ORIGINAL command that failed: '{cmd}'"
        )
        return tool_result_dict

    console.print(f"[yellow]Binary wheel unavailable for '{pkg}', trying source build...[/yellow]")
    proc2 = subprocess.run(
        ["pip", "install", pkg],
        capture_output=True, text=True
    )
    if proc2.returncode == 0:
        out2 = (proc2.stdout or "").strip()[-300:]
        console.print(f"[green]pip install {pkg} succeeded (source).[/green]")
        tool_result_dict["success"] = True
        tool_result_dict["stdout"] += (
            f"\n\n[Auto-install '{pkg}' OK (source)]\n{out2}\n"
            f"AUTO INSTALL SUCCESSFUL: {pkg}\n"
            f"CRITICAL INSTRUCTION: DO NOT RUN PIP INSTALL AGAIN.\n"
            f"The package '{pkg}' is now fully available. Immediately retry the ORIGINAL command that failed: '{cmd}'"
        )
        return tool_result_dict

    err = (proc2.stderr or proc2.stdout or "").strip()[-400:]
    console.print(f"[red]pip install {pkg} failed.[/red]")
    tool_result_dict["success"] = False
    tool_result_dict["stderr"] += (
        f"\n\n[Auto-install '{pkg}' FAILED]\n{err}\n"
        f"CRITICAL AGENT NOTE: Compilation or installation failed. "
        f"Do NOT attempt to run pip install or install_package for '{pkg}' again. "
        f"Report the failure to the user and ask them to resolve it manually."
    )
    return tool_result_dict


def _extract_embedded_tool_call(text):
    n = len(text)
    search_from = 0
    while True:
        start = text.find("{", search_from)
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        end = None
        for i in range(start, n):
            c = text[i]
            if in_string:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end is None:
            return None
        candidate = text[start:end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and parsed.get("type") == "tool_call":
                return parsed
        except Exception:
            pass
        search_from = start + 1


def _infer_expected_artifacts(user_input, plan_steps):
    """Combines explicit extraction, plan blueprinting, and structural heuristics."""
    artifacts = set()
    # Explicitly filter by standard extensions to avoid matching programmatic properties or dot methods
    file_pattern = re.compile(r"([a-zA-Z0-9_\-\.\/]+\.(?:py|html|css|json|md|txt|sh|js))")

    for step in plan_steps:
        matches = file_pattern.findall(str(step))
        for m in matches:
            if not m.startswith(("http", "pip", "python")):
                artifacts.add(normalize_path(m))

    matches = file_pattern.findall(user_input)
    for m in matches:
        if not m.startswith(("http", "pip", "python")):
            artifacts.add(normalize_path(m))

    return artifacts


def main(session):
    watchdog.start()
    BANNER = """[bold purple]
    ╔══════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║     █████╗ ██████╗ ██╗   ██╗███████╗███████╗                   ║
    ║    ██╔══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██╔════╝                   ║
    ║    ███████║██████╔╝ ╚████╔╝ ███████╗███████╗                   ║
    ║    ██╔══██║██╔══██╗  ╚██╔╝  ╚════██║╚════██║                   ║
    ║    ██║  ██║██████╔╝   ██║   ███████║███████║                   ║
    ║    ╚═╝  ╚═╝╚═════╝    ╚═╝   ╚══════╝╚══════╝                   ║
    ║                                                                ║
    ║      ██████╗ ███████╗███████╗██╗███████╗                       ║
    ║     ██╔═══██╗██╔════╝██╔════╝██║██╔════╝                       ║
    ║     ██║   ██║███████╗███████╗██║███████╗                       ║
    ║     ██║   ██║╚════██║╚════██║██║╚════██║                       ║
    ║     ╚██████╔╝███████║███████║██║███████║                       ║
    ║      ╚═════╝ ╚══════╝╚══════╝╚═╝╚══════╝                       ║
    ║                                                                ║
    ╚══════════════════════════════════════════════════════════════════╝[/bold purple]"""

    console.print(BANNER)
    console.print(f"  [dim] Local AI Coding Agent · {DEFAULT_MODEL} · Ollama [/dim]")
    console.print(f"  [dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]")
    console.print(f"  [bold white]Workspace:[/bold white]  [cyan]{session.root}[/cyan]")
    console.print(f"  [bold white]Memory:[/bold white]     [cyan]{session.memory_path}[/cyan]")
    console.print(f"  [bold white]Index:[/bold white]      [cyan]{session.index_path}[/cyan]")
    console.print(f"  [dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]")
    console.print(f"  [dim]Type a question, a /command, or /exit to quit.[/dim]\n")

    while True:
        global metrics
        metrics = MetricsTracker()
        
        try:
            user_input = input("\n> ").strip()
            if not user_input:
                continue

            if user_input == "/exit":
                break

            session.log(f"USER: {user_input}")

            if user_input.startswith("/remember"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[red]Usage: /remember <key> <value>[/red]")
                    continue
                from systems.memory import remember
                remember(session, parts[1], parts[2])
                console.print(f"[green]Remembered: {parts[1]} = {parts[2]}[/green]")
                continue

            if user_input.startswith("/forget"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    console.print("[red]Usage: /forget <key>[/red]")
                    continue
                from systems.memory import forget
                if forget(session, parts[1]):
                    console.print(f"[green]Forgot: {parts[1]}[/green]")
                else:
                    console.print(f"[yellow]Key not found: {parts[1]}[/yellow]")
                continue

            if user_input == "/memory":
                from systems.memory import get_memory
                console.print("[cyan]Project Memory:[/cyan]")
                console.print(str(get_memory(session)), markup=False)
                continue

            if user_input == "/index":
                console.print("[yellow]Rebuilding project index from scratch...[/yellow]")
                if os.path.exists(session.index_path):
                    os.remove(session.index_path)
                index = build_index(session.root)
                save_index(session, index)
                console.print(f"[cyan]AST index built: {len(index)} entities.[/cyan]")
                console.print("[yellow]Syncing FAISS semantic index...[/yellow]")
                sync_faiss_with_ast(index)
                console.print("[green]Project indexed. AST + FAISS ready.[/green]")
                continue

            if user_input == "/showindex":
                index = load_index(session)
                console.print("[cyan]Current Index:[/cyan]")
                console.print(str(index), markup=False)
                continue

            if user_input.startswith("/find"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    console.print("[red]Usage: /find <keyword>[/red]")
                    continue
                results = search_index(session, parts[1])
                console.print("[bold magenta]Search Results:[/bold magenta]")
                console.print(str(results), markup=False)
                continue

            if user_input.startswith("/ls"):
                _ls_res = list_files()
                console.print(_ls_res.stdout if _ls_res.success else _ls_res.stderr, style="cyan", markup=False)
                continue

            if user_input.startswith("/health"):
                console.print(watchdog.health())
                continue

            if user_input.startswith("/read"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    console.print("[red]Usage: /read <filename>[/red]")
                    continue
                filename = parts[1]
                res = read_file(filename)
                if not res.success:
                    console.print(res.stderr, markup=False)
                else:
                    console.print(f"--- START OF FILE: {filename} ---", markup=False)
                    console.print(res.stdout, markup=False)
                    console.print(f"--- END OF FILE: {filename} ---", markup=False)
                continue

            if user_input.startswith("/write"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[red]Usage: /write <filename> <content>[/red]")
                    continue
                path, content = parts[1], parts[2]
                content = content.replace("\\n", "\n")
                result = write_file(path, content)
                if result.success:
                    console.print(result.summary, style="green", markup=False)
                    try:
                        update_file_index(session, path)
                        console.print("[dim]Index updated.[/dim]")
                    except Exception as e:
                        console.print("[yellow]Index update failed: [/yellow]", end="")
                        console.print(str(e), markup=False, highlight=False)
                else:
                    console.print(result.stderr, style="red", markup=False)
                continue

            if user_input.startswith("/edit"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[red]Usage: /edit <file> <instruction>[/red]")
                    continue
                path, instruction = parts[1], parts[2]
                read_res = read_file(path)
                if not read_res.success:
                    console.print(f"[red]Failed to read file: {read_res.stderr}[/red]")
                    continue
                old_code = read_res.stdout
                prompt = build_edit_prompt(path, instruction)
                edited_code = run_worker(
                    session, {"task_type": "editing"},
                    [{"role": "user", "content": prompt}], None
                )
                edited_code = edited_code.strip()
                if edited_code.startswith("```"):
                    lines = edited_code.splitlines()[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    edited_code = "\n".join(lines)
                diff_lines = show_diff(old_code, edited_code)
                console.print("\n[cyan]Proposed Changes:[/cyan]")
                for line, style in diff_lines:
                    if style:
                        console.print(line, style=style, markup=False, highlight=False)
                    else:
                        console.print(line, markup=False, highlight=False)
                confirm = input("\nApply changes? (y/n): ").lower()
                if confirm == "y":
                    write_res = write_file(path, edited_code)
                    if write_res.success:
                        console.print("[green]File updated.[/green]")
                        try:
                            update_file_index(session, path)
                            console.print("[dim]Index updated.[/dim]")
                        except Exception as e:
                            console.print("[yellow]Index update failed: [/yellow]", end="")
                            console.print(str(e), markup=False, highlight=False)
                    else:
                        console.print(f"[red]Failed to save edit: {write_res.stderr}[/red]")
                else:
                    console.print("[yellow]Edit cancelled.[/yellow]")
                continue

            # ── TOOL AUTO-DETECTION ───────────────────────────────────────
            tool = detect_tool(user_input)
            if tool:
                console.print(f"[dim]Tool detected: {tool['tool']}[/dim]")
                if tool["tool"] == "ls":
                    ls_res = list_files()
                    console.print(ls_res.stdout if ls_res.success else ls_res.stderr, style="cyan", markup=False)
                elif tool["tool"] == "read":
                    r_res = read_file(tool["path"])
                    console.print(r_res.stdout if r_res.success else r_res.stderr, markup=False)
                continue

            # ── TASK CLASSIFICATION ──────────────────────────────────────────
            watchdog.set_required_model(config.PLANNER_MODEL)
            watchdog.check()
            metrics.record_llm_call()
            task = classify_task(user_input)
            console.print(f"[yellow]Task: {task}[/yellow]")

            auto_context = []
            if task.get('needs_retrieval', True):
                auto_context = search_index(session, user_input)
            full_context = None
            if auto_context:
                full_context = build_context(auto_context)
                console.print(f"[dim]Retrieved {len(auto_context)} context match(es).[/dim]")

            if requires_more_info(task, user_input) and not auto_context:
                console.print("[yellow]I need clarification before continuing.[/yellow]")
                clarification = input("Reply with option or full path (or 'n' to stop): ")
                if clarification.lower() == 'n':
                    continue
                user_input += "\nCLARIFICATION: " + clarification

            if task.get("needs_planner"):
                from core.planner import generate_plan
                console.print("[yellow]Generating execution plan...[/yellow]")
                metrics.record_llm_call()
                plan_steps = generate_plan(user_input, full_context)
                console.print("\n[bold cyan]Execution Plan:[/bold cyan]")
                for i, step in enumerate(plan_steps, 1):
                    console.print(f"  {i}. ", style="cyan", end="")
                    console.print(str(step), markup=False)
                plan_str = "Execution Plan:\n" + "\n".join(
                    f"{i}. {s}" for i, s in enumerate(plan_steps, 1)
                )
                full_context = (full_context + "\n\n" + plan_str) if full_context else plan_str
            else:
                plan_steps = []

            # Extract expected blueprints uniformly using the master normalization engine
            expected_files = {normalize_path(p) for p in _infer_expected_artifacts(user_input, plan_steps)}

            # State Machine: Check if the plan specifically mandates validation or testing verification commands
            has_validation_commands = any(
                any(keyword in str(step).lower() for keyword in ["run", "python", "pytest", "test", "execute"])
                for step in plan_steps
            )
            if has_validation_commands:
                console.print("[dim]Runtime State Machine initialized: Awaiting verification phase execution.[/dim]")

            state.add_message("user", user_input)

            max_passes     = 3 if task.get("task_type") == "coding" else 2
            passes         = 0
            worker_history = list(state.messages)
            if task.get("task_type") in ("chat", "explanation"):
                worker_history = worker_history[-6:]
            max_tool_loops = 8 if task.get("task_type") == "coding" else 3
            tool_loops     = 0
            parse_fail_count = 0
            response_content = ""

            # Unified Tracking Databases
            exec_state = ExecutionState(task_type=task.get("task_type", "chat"))
            content_signatures = set()
            tool_signatures_counter = defaultdict(int)
            
            # Stateful Verification Tracking Switches
            last_tool_metadata = None
            last_successful_tool_sig = None
            last_successful_tool_result_str = ""
            task_completed = False

            # ── Skill selector + OpenSpec (lazy, zero cost for chat) ──────────
            skill_text = select_skills(task.get("task_type"), user_input)
            open_spec  = build_open_spec(user_input, task)

            if os.environ.get("DEBUG"):
                if skill_text:
                    console.print(f"[dim]Skills loaded: {len(skill_text)} chars[/dim]")
                if open_spec:
                    console.print(f"[dim]OpenSpec: {open_spec.render()}[/dim]")

            # ── Auto-read files mentioned in edit/coding prompts ──────────────
            _AUTO_READ_ACTIONS = [
                "improve", "update", "edit", "enhance", "redesign", "rewrite",
                "change", "modify", "fix", "refactor",
            ]
            _text_lower = user_input.lower()
            _should_auto_read = (
                task.get("task_type") in ("coding", "debugging", "file_analysis")
                and any(w in _text_lower for w in _AUTO_READ_ACTIONS)
            )
            if _should_auto_read:
                import re as _re
                import os as _os
                _file_pat = _re.compile(
                    r"\b([\w./\\-]+)(?:\.| )(py|js|ts|html|css|json|yaml|yml|md|txt|toml|cfg|ini|sh)\b",
                    _re.IGNORECASE
                )
                _mentioned = _file_pat.findall(user_input)
                
                if _mentioned:
                    _all_files = list_files().stdout.splitlines()
                    
                for _base, _ext in _mentioned[:2]:  # cap at 2 files
                    _f_name = f"{_base}.{_ext}"
                    _fpath = _f_name
                    
                    if not _os.path.exists(_fpath):
                        # Find all matching paths in list_files() output
                        _matches = [p for p in _all_files if p.endswith(_f_name) or _f_name in p]
                        if _matches:
                            # Pick the shortest path (closest to root)
                            _fpath = min(_matches, key=len)
                            
                    _norm = normalize_path(_fpath)
                    if _norm not in exec_state.files_read:
                        res = read_file(_fpath)
                        if res.success:
                            console.print(f"[dim]Auto-read: {_fpath}[/dim]")
                            exec_state.files_read.add(_norm)
                            worker_history.append({
                                "role": "user",
                                "content": f"FILE CONTENTS ({_fpath}):\n{res.stdout}\n\nI have automatically read this file for you. Do NOT call read_file for it. Use this content to immediately begin planning your edits, or call write_file/replace_chunk to apply them."
                            })

            # Mode Management
            worker_mode = "execute"
            all_tools_executed = set()
            
            while passes < max_passes and tool_loops < max_tool_loops:
                if metrics.reasoning_passes >= metrics.max_reasoning_passes:
                    console.print("[red]Maximum reasoning passes reached. Emergency stop.[/red]")
                    break

                prompt_size  = sum(len(m.get("content", "")) for m in worker_history)
                context_size = len(full_context or "")
                console.print(f"[dim]Prompt chars={prompt_size}, Context chars={context_size}[/dim]")

                call_start = time.time()
                metrics.record_llm_call()
                
                # Chat and Explanation tasks bypass tools entirely
                if task.get("task_type") in ("chat", "explanation"):
                    worker_mode = "chat"
                    
                response_stream = run_worker(session, task, worker_history, full_context,
                                              stream=True, skill_text=skill_text, open_spec=open_spec, worker_mode=worker_mode)
                
                raw_response = ""
                
                if worker_mode in ("chat", "respond"):
                    console.print("\n[bold green]Assistant:[/bold green] ", end="")
                    for chunk in response_stream:
                        print(chunk, end="", flush=True)
                        raw_response += chunk
                    print()
                    state.add_message("assistant", raw_response)
                    task_completed = True
                    break
                
                elif worker_mode == "execute":
                    # Stream and print ONLY the <think> blocks if present, otherwise silent
                    in_think_block = False
                    think_buffer = ""
                    for chunk in response_stream:
                        raw_response += chunk
                        think_buffer += chunk
                        if not in_think_block and "<think>" in think_buffer:
                            in_think_block = True
                            idx = think_buffer.find("<think>") + 7
                            console.print(think_buffer[idx:], end="", style="dim", markup=False)
                            think_buffer = ""
                        elif in_think_block:
                            if "</think>" in chunk:
                                idx = chunk.find("</think>")
                                console.print(chunk[:idx], end="", style="dim", markup=False)
                                console.print()
                                in_think_block = False
                            else:
                                console.print(chunk, end="", style="dim", markup=False)

                    # ── Parse Strict JSON ─────────────────────────────────────
                    parsed_response = None
                    try:
                        text = raw_response.strip()
                        if text.startswith("<think>"):
                            end_tag = text.find("</think>")
                            if end_tag != -1:
                                text = text[end_tag + len("</think>"):].strip()
                        if text.startswith("```json"): text = text[7:]
                        elif text.startswith("```"): text = text[3:]
                        if text.endswith("```"): text = text[:-3]
                        
                        parsed_response = json.loads(text.strip())
                    except Exception:
                        # Fallback: extract first ```json ... ``` block from mixed prose
                        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
                        if fence_match:
                            try:
                                parsed_response = json.loads(fence_match.group(1))
                            except Exception:
                                pass
                        if not parsed_response:
                            console.print("[dim]Worker produced an invalid response. Retrying...[/dim]")
                        
                    if not parsed_response:
                        parse_fail_count += 1
                        if parse_fail_count >= 3:
                            console.print("[red]Worker failed to produce valid JSON after 3 attempts. Aborting task.[/red]")
                            response_content = "[Task aborted due to malformed worker output]"
                            break

                        worker_history.append({"role": "assistant", "content": raw_response})
                        worker_history.append({
                            "role": "user",
                            "content": (
                                "Your response must be exactly one JSON object. "
                                "No markdown, no prose, no code blocks."
                            )
                        })
                        tool_loops += 1
                        metrics.record_retry()
                        continue  # Validator is NOT reached — parsed_response is falsy

                    parsed_responses = parsed_response if isinstance(parsed_response, list) else [parsed_response]
                    parse_fail_count = 0  # reset on successful parse
                    
                    has_final = any(isinstance(pr, dict) and pr.get('type') == 'final' for pr in parsed_responses)
                    if has_final:
                        # ── Strict Completion Verification ──
                        # NOTE: This block is only reachable after a successful parse.
                        # Parse failures hit `continue` above and never reach here.
                        passed, instruction = validate_post_tool(exec_state)
                        
                        if not passed:
                            console.print(f"[yellow]Validator rejected completion: {instruction}[/yellow]")
                            worker_history.append({"role": "assistant", "content": raw_response})
                            worker_history.append({"role": "user", "content": f"Validation failed: {instruction}. You must use tools to satisfy the contract before declaring final."})
                            tool_loops += 1
                            metrics.record_retry()
                            continue
                            
                        all_tools = {evt.tool for evt in exec_state.tool_events}
                        read_only_tools = {"read_file", "list_files"}
                        if all_tools and all_tools.issubset(read_only_tools):
                            console.print("[dim]Read-only operation complete. Skipping RESPOND loop.[/dim]")
                            last_event = next((evt for evt in reversed(exec_state.tool_events) if evt.success), None)
                            if last_event and last_event.stdout:
                                console.print("\n[bold cyan]Output:[/bold cyan]")
                                console.print(last_event.stdout)
                            task_completed = True
                            break
                            
                        console.print("[dim]Execution complete. Generating final response...[/dim]")
                        
                        # Clear history to prevent LLM hallucination and force it to rely ONLY on execution facts
                        transcript = exec_state.render_transcript()
                        worker_history.clear()
                        worker_history.append({
                            'role': 'user', 
                            'content': f"You have successfully completed the tasks. Here is the execution summary:\n\n{transcript}\n\nPlease output a plain text response summarizing the final resolution for the user based strictly on this factual execution summary."
                        })
                        worker_mode = "respond"
                        continue
                    has_tool_call = any(isinstance(pr, dict) and pr.get('type') == 'tool_call' for pr in parsed_responses)
                    if has_tool_call:
                        worker_history.append({'role': 'assistant', 'content': raw_response})
                        last_tools_executed = []
                    batch_results = []
                    any_failed = False
                    for pr in parsed_responses:
                        if not isinstance(pr, dict): continue
                        parsed_response = pr
                        resp_type = parsed_response.get('type')


                        if resp_type == "tool_call" and tool_loops < max_tool_loops:
                            metrics.tool_calls += 1
                            raw_tool_name = parsed_response.get("tool")
                            tool_name = TOOL_ALIASES.get(raw_tool_name, raw_tool_name)
                            last_tools_executed.append(tool_name)
                            all_tools_executed.add(tool_name)
                            args      = parsed_response.get("args", {})
                            console.print("\n[magenta]Tool Call:[/magenta] ", end="")
                            console.print(f"{tool_name}({args})", markup=False, highlight=False)
                            session.log(f"TOOL: {tool_name}({args})")

                            # ── 🛑 Hard Stop Guards (Abort Batch on invalid tools) ──
                            VALID_TOOLS = {"read_file", "write_file", "replace_chunk", "patch_file", "list_files", "search_index", "run_command"}
                            if tool_name not in VALID_TOOLS:
                                err_msg = f"Error: Unknown tool '{tool_name}'"
                                console.print(f"[red]{err_msg}[/red]")
                                batch_results.append(json.dumps({"success": False, "tool": tool_name, "stderr": err_msg}, indent=2))
                                any_failed = True
                                break  # Do NOT execute follow-up steps in this batch

                            # Enforce task_type constraints
                            task_t = task.get("task_type")
                            if task_t == "execute" and tool_name in {"replace_chunk", "write_file", "patch_file"}:
                                err_msg = f"Tool {tool_name} is not appropriate for execute tasks. Use run_command."
                                console.print(f"[yellow]{err_msg}[/yellow]")
                                batch_results.append(json.dumps({"success": False, "tool": tool_name, "stderr": err_msg}, indent=2))
                                any_failed = True
                                break
                            
                            if task_t == "file_analysis" and tool_name in {"replace_chunk", "write_file", "patch_file"}:
                                err_msg = f"Tool {tool_name} is not appropriate for file_analysis tasks. This is a read-only task."
                                console.print(f"[yellow]{err_msg}[/yellow]")
                                batch_results.append(json.dumps({"success": False, "tool": tool_name, "stderr": err_msg}, indent=2))
                                any_failed = True
                                break

                            # Signature Loop Guard Check
                            sig_key = (tool_name, json.dumps(args, sort_keys=True))
                            
                            if sig_key == last_successful_tool_sig:
                                console.print(f"[yellow]Skipping duplicate successful tool call: {tool_name}[/yellow]")
                                batch_results.append(f'TOOL RESULT (CACHED):\n{last_successful_tool_result_str}\n\nCRITICAL INSTRUCTION: You already called this tool successfully. Produce the final answer NOW. Do not call this tool again.')
                                continue
                                
                            tool_signatures_counter[sig_key] += 1
                        
                            if tool_signatures_counter[sig_key] >= 3:
                                console.print(f"[bold red]CRITICAL: Infinite loop flagged for tool '{tool_name}'![/bold red]")
                                response_content = f"Execution halted: Duplicate processing loop detected inside tool execution call."
                                break

                            tool_result_dict = {"success": True, "tool": tool_name, "stdout": "", "stderr": ""}
                            
                            # Robustly extract path from common LLM keys
                            raw_path = args.get("path") or args.get("file_path") or args.get("filename") or args.get("file")
                            norm_path = normalize_path(raw_path)
                            
                            if os.environ.get("DEBUG"):
                                console.print(f"[magenta]DEBUG dispatcher tool={tool_name}[/magenta]")
                                console.print(f"[magenta]DEBUG extracted args: {args}[/magenta]")
                                console.print(f"[magenta]DEBUG raw_path: {raw_path}[/magenta]")
                                console.print(f"[magenta]DEBUG norm_path: {norm_path}[/magenta]")

                            try:
                                start_time = time.time()
                                tool_res = None
                                
                                if tool_name == "read_file":
                                    tool_res = read_file(raw_path)
                                    if tool_res.success:
                                        exec_state.files_read.add(norm_path)
                                        
                                elif tool_name == "write_file" and not task_completed:
                                    new_content = args.get("content", "").strip()
                                    tool_res = write_file(raw_path, new_content)
                                    if tool_res.success:
                                        exec_state.files_written.add(norm_path)
                                        try:
                                            update_file_index(session, raw_path)
                                        except Exception:
                                            pass

                                elif tool_name == "replace_chunk":
                                    target  = args.get("target_code", "")
                                    replace = args.get("replacement_code", "").strip()
                                    tool_res = replace_chunk(raw_path, target, replace, content_signatures)
                                    if tool_res.success:
                                        exec_state.files_written.add(norm_path)
                                        try:
                                            update_file_index(session, raw_path)
                                        except Exception:
                                            pass

                                elif tool_name == "list_files":
                                    tool_res = list_files()

                                elif tool_name == "search_index":
                                    # Fallback to direct call with mock tool result
                                    out = str(search_index(session, args.get("query")))
                                    tool_res = ToolResult(success=True, stdout=out, summary="Searched index")

                                elif tool_name == "run_command":
                                    cmd = args.get("command", "").strip()
                                    
                                    # Duplicate command guard
                                    last_run = next((e for e in reversed(exec_state.tool_events) if e.tool == "run_command"), None)
                                    if last_run and last_run.args.get("command", "").strip() == cmd:
                                        tool_res = ToolResult(
                                            success=False,
                                            stdout="",
                                            stderr="DUPLICATE COMMAND GUARD TRIPPED: You just ran this exact command. If it succeeded and no further action is needed, output a 'final' response. Do not repeat identical commands.",
                                            summary="Duplicate command blocked."
                                        )
                                    else:
                                        tool_res = run_command(cmd, session.root)
                                        if tool_res.success:
                                            exec_state.commands_run.append(cmd)

                                else:
                                    # This should never be reached due to VALID_TOOLS guard, but kept for safety
                                    tool_res = ToolResult(success=False, stdout="", stderr=f"Error: Unknown tool '{tool_name}'", summary="Unknown tool")

                            except BaseException as e:
                                is_interrupt = isinstance(e, KeyboardInterrupt)
                                err_msg = "Process interrupted by user (Ctrl+C)." if is_interrupt else f"Tool Execution Error: {e}"
                                status_str = "interrupted" if is_interrupt else "failed"
                                tool_res = ToolResult(
                                    success=False,
                                    status=status_str,
                                    stdout="",
                                    stderr=err_msg,
                                    summary=err_msg
                                )

                            finally:
                                end_time = time.time()
                                if tool_res is None:
                                    tool_res = ToolResult(success=False, status="failed", stdout="", stderr="Tool failed to return a result.", summary="Unknown error")

                                exec_state.tool_events.append(ToolEvent(
                                    tool=tool_name,
                                    args=args,
                                    success=tool_res.success,
                                    started_at=start_time,
                                    finished_at=end_time,
                                    result_summary=tool_res.summary,
                                    status=getattr(tool_res, "status", "completed"),
                                    is_long_running=getattr(tool_res, "is_long_running", False),
                                    stdout=tool_res.stdout,
                                    error=tool_res.stderr if not tool_res.success else None
                                ))
                                
                                tool_result_dict["success"] = tool_res.success
                                tool_result_dict["stdout"] = tool_res.stdout
                                tool_result_dict["stderr"] = tool_res.stderr

                            last_tool_metadata = {
                                "tool": tool_name,
                                "success": tool_result_dict["success"],
                                "path": raw_path if raw_path else args.get("command", "")
                            }

                            combined_result_str = json.dumps(tool_result_dict, indent=2)
                            console.print(f"[dim]Tool Result: {len(combined_result_str)} chars[/dim]")

                            if tool_result_dict["success"]:
                                last_successful_tool_sig = sig_key
                                last_successful_tool_result_str = combined_result_str
                                
                                if tool_name == "read_file":
                                    combined_result_str += "\n\nThe requested file has already been read successfully. Use the provided contents to answer the user. Do NOT call read_file again unless requesting a different file."

                        batch_results.append(f'TOOL RESULT:\n{combined_result_str}')
                        if not tool_result_dict['success']:
                            any_failed = True
                            last_tools_failed = True

                    if batch_results:
                        if tool_loops >= max_tool_loops - 1:
                            instruction = "TOOL LOOP LIMIT REACHED. You must now produce the final user-facing answer in plain text. Do NOT emit any more tool calls."
                        else:
                            instruction = "Here are the tool results. If you need more information, you may use another tool. Otherwise, produce the final user-facing answer."
                        
                        worker_history.append({
                            'role': 'user',
                            'content': '\n\n'.join(batch_results) + f'\n\n{instruction}'
                        })
                        if any_failed:
                            worker_history.append({'role': 'user', 'content': 'Some tool calls failed. Correct and retry.'})
                        tool_loops += 1
                        metrics.record_retry()
                        continue

                    response_items = [pr for pr in parsed_responses if isinstance(pr, dict) and pr.get('type') == 'response']
                    if response_items:
                        response_content = ' '.join(pr.get('content', '') for pr in response_items)
                        console.print() 
                        console.print(response_content, style='green', markup=False, highlight=False)
                        worker_history.append({'role': 'assistant', 'content': response_content})
                if not response_content or not response_content.strip():
                    response_content = "[empty response from model]"

                if task_completed:
                    break
                else:
                    break

            session.log(f"AGENT: {response_content}")
            state.add_message("assistant", response_content)

            ctx_size = len(locals().get("full_context") or "")
            console.print(metrics.finish_task(context_size=ctx_size))
            
            from systems.ollama_client import unload_active_models
            unload_active_models()

        except ResourceSafetyError as e:
            console.print(f"\n{e}\n", markup=False)
            metrics.resource_failures += 1
            watchdog.wait_for_cooldown()
            
            from systems.ollama_client import unload_active_models
            unload_active_models()
        except RuntimeError as e:
            console.print("[bold yellow]Agent Error:[/bold yellow] ", end="")
            console.print(str(e), markup=False, highlight=False)
        except (KeyboardInterrupt, EOFError, StopIteration):
            console.print("\n[yellow]Interrupted.[/yellow]")
            break
        except Exception as e:
            logger.critical(f"Unexpected error: {e}", exc_info=True)
            console.print("[bold red]Unexpected Error:[/bold red] ", end="")
            console.print(str(e), markup=False, highlight=False)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        console.print("[red]Usage: python cli.py run <project_path>[/red]")
        sys.exit(1)

    project_path = sys.argv[2]
    session = ProjectSession(project_path)

    if not os.path.exists(session.index_path):
        console.print("[yellow]Project not indexed. Initializing...[/yellow]")
        index = build_index(session.root)
        with open(session.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        session.log("Project initialized")
        console.print("[green]Initialization complete.[/green]")

    main(session)