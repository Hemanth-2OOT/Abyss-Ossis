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
print("CWD:", os.getcwd())
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

from tools.file_reader import read_file
from tools.file_writer import write_file
from tools.directory_reader import list_files
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
                console.print(list_files(), style="cyan", markup=False)
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
                content = read_file(filename)
                if str(content).startswith("Error"):
                    console.print(content, markup=False)
                else:
                    console.print(f"--- START OF FILE: {filename} ---", markup=False)
                    console.print(content, markup=False)
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
                console.print(result, style="green", markup=False)
                try:
                    update_file_index(session, path)
                    console.print("[dim]Index updated.[/dim]")
                except Exception as e:
                    console.print("[yellow]Index update failed: [/yellow]", end="")
                    console.print(str(e), markup=False, highlight=False)
                continue

            if user_input.startswith("/edit"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[red]Usage: /edit <file> <instruction>[/red]")
                    continue
                path, instruction = parts[1], parts[2]
                old_code = read_file(path)
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
                    write_file(path, edited_code)
                    console.print("[green]File updated.[/green]")
                    try:
                        update_file_index(session, path)
                        console.print("[dim]Index updated.[/dim]")
                    except Exception as e:
                        console.print("[yellow]Index update failed: [/yellow]", end="")
                        console.print(str(e), markup=False, highlight=False)
                else:
                    console.print("[yellow]Edit cancelled.[/yellow]")
                continue

            # ── TOOL AUTO-DETECTION ───────────────────────────────────────
            tool = detect_tool(user_input)
            if tool:
                console.print(f"[dim]Tool detected: {tool['tool']}[/dim]")
                if tool["tool"] == "ls":
                    console.print(list_files(), style="cyan", markup=False)
                elif tool["tool"] == "read":
                    console.print(read_file(tool["path"]), markup=False)
                continue

            # ── TASK CLASSIFICATION ──────────────────────────────────────────
            watchdog.set_required_model(config.PLANNER_MODEL)
            watchdog.check()
            metrics.record_llm_call()
            task = classify_task(user_input)
            console.print(f"[yellow]Task: {task}[/yellow]")

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
            max_tool_loops = 8 if task.get("task_type") == "coding" else 3
            tool_loops     = 0
            response_content = ""

            # Unified Tracking Databases
            _written_files = set()
            content_signatures = set()
            tool_signatures_counter = defaultdict(int)
            duplicate_count = defaultdict(int)
            
            # Stateful Verification Tracking Switches
            runtime_verified = False
            last_tool_metadata = None
            task_completed = False

            while passes < max_passes and tool_loops < max_tool_loops:
                prompt_size  = sum(len(m.get("content", "")) for m in worker_history)
                context_size = len(full_context or "")
                console.print(f"[dim]Prompt chars={prompt_size}, Context chars={context_size}[/dim]")

                call_start = time.time()
                metrics.record_llm_call()
                response_stream = run_worker(session, task, worker_history, full_context, stream=True)
                console.print(
                    f"[dim]run_worker returned generator in {time.time()-call_start:.2f}s[/dim]"
                )

                raw_response     = ""
                is_tool          = None
                detect_buffer    = ""
                MIN_DETECT_CHARS = 8
                MAX_THINK_BUFFER = 20000
                first_chunk_time = None
                chunk_count      = 0
                stream_error     = None

                chunk_queue = Queue()

                def _consume_stream(stream, q):
                    try:
                        for c in stream:
                            q.put(("chunk", c))
                    except Exception as e:
                        q.put(("error", e))
                    finally:
                        q.put(("done", None))

                producer = Thread(
                    target=_consume_stream,
                    args=(response_stream, chunk_queue),
                    daemon=True
                )
                producer.start()

                in_think_block  = False
                think_seen_open = False

                while True:
                    try:
                        kind, payload = chunk_queue.get(timeout=3)
                    except Empty:
                        console.print("[dim]...thinking...[/dim]")
                        continue

                    if kind == "done":
                        break
                    if kind == "error":
                        stream_error = payload
                        break

                    chunk = payload
                    chunk_count += 1
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                        console.print(
                            f"[dim]First chunk after {first_chunk_time - call_start:.2f}s[/dim]"
                        )

                    raw_response += chunk

                    if is_tool is None:
                        detect_buffer += chunk
                        if not think_seen_open:
                            stripped_full = detect_buffer.lstrip()
                            if stripped_full.startswith("<think>"):
                                think_seen_open = True
                                in_think_block  = True
                                detect_buffer   = stripped_full[len("<think>"):]
                            else:
                                stripped = stripped_full
                                if len(stripped) >= MIN_DETECT_CHARS or "\n" in stripped:
                                    if stripped.startswith("{"):
                                        is_tool = True
                                    else:
                                        is_tool = False
                                        console.print()
                                        console.print(
                                            stripped, end="", style="green",
                                            markup=False, highlight=False
                                        )
                        if in_think_block:
                            if len(detect_buffer) > MAX_THINK_BUFFER:
                                detect_buffer = detect_buffer[-5000:]
                            end_tag = detect_buffer.find("</think>")
                            if end_tag != -1:
                                in_think_block = False
                                remainder      = detect_buffer[end_tag + len("</think>"):].lstrip()
                                detect_buffer  = remainder
                                if remainder and (
                                    len(remainder) >= MIN_DETECT_CHARS or "\n" in remainder
                                ):
                                    if remainder.startswith("{"):
                                        is_tool = True
                                    else:
                                        is_tool = False
                                        console.print()
                                        console.print(
                                            remainder, end="", style="green",
                                            markup=False, highlight=False
                                        )
                    elif not is_tool:
                        console.print(chunk, end="", style="green", markup=False, highlight=False)

                producer.join(timeout=1)
                console.print(f"[dim]Chunks received: {chunk_count}[/dim]")
                if not is_tool:
                    console.print()

                if stream_error is not None:
                    response_content = f"[Worker stream error: {stream_error}]"
                    console.print(f"[red]Worker stream raised an error: {stream_error}[/red]")
                    break
                if chunk_count == 0:
                    response_content = "[Worker returned empty stream]"
                    console.print("[red]Worker yielded zero chunks — check Ollama.[/red]")
                    break

                # ── Parse ─────────────────────────────────────────────────
                parsed_response = None

                if is_tool:
                    try:
                        text = raw_response.strip()
                        if text.startswith("<think>"):
                            end_tag = text.find("</think>")
                            if end_tag != -1:
                                text = text[end_tag + len("<think>"):].strip()
                        if text.startswith("```json"):
                            text = text[7:]
                        elif text.startswith("```"):
                            text = text[3:]
                        if text.endswith("```"):
                            text = text[:-3]
                        parsed_response = json.loads(text.strip())
                    except Exception as e:
                        console.print(f"[red]JSON parse failed: {e}[/red]")
                else:
                    parsed_response = _extract_embedded_tool_call(raw_response)
                    if parsed_response:
                        console.print(
                            "[dim](Recovered tool_call embedded in narrated response.)[/dim]"
                        )

                if is_tool and parsed_response is None:
                    console.print(
                        "[yellow]Tool JSON invalid/truncated — asking model to retry.[/yellow]"
                    )
                    worker_history.append({"role": "assistant", "content": raw_response})
                    worker_history.append({
                        "role": "user",
                        "content": (
                            "Your tool_call JSON was invalid or truncated. "
                            "Output ONLY valid JSON starting with '{'. "
                            "No prose narration, no markdown wrappers, no plans. Retry the exact same action now."
                        )
                    })
                    tool_loops += 1
                    metrics.record_retry()
                    continue

                if parsed_response and isinstance(parsed_response, dict):
                    resp_type = parsed_response.get("type")

                    if resp_type == "tool_call" and tool_loops < max_tool_loops:
                        metrics.tool_calls += 1
                        tool_name = parsed_response.get("tool")
                        args      = parsed_response.get("args", {})
                        console.print("\n[magenta]Tool Call:[/magenta] ", end="")
                        console.print(f"{tool_name}({args})", markup=False, highlight=False)
                        session.log(f"TOOL: {tool_name}({args})")

                        # Signature Loop Guard Check
                        sig_key = (tool_name, json.dumps(args, sort_keys=True))
                        tool_signatures_counter[sig_key] += 1
                        
                        if tool_signatures_counter[sig_key] >= 3:
                            console.print(f"[bold red]CRITICAL: Infinite loop flagged for tool '{tool_name}'![/bold red]")
                            response_content = f"Execution halted: Duplicate processing loop detected inside tool execution call."
                            break

                        tool_result_dict = {"success": True, "tool": tool_name, "stdout": "", "stderr": ""}
                        raw_path = args.get("path")
                        norm_path = normalize_path(raw_path)

                        try:
                            if tool_name == "read_file":
                                res = read_file(raw_path)
                                if str(res).startswith("Error:"):
                                    tool_result_dict["success"] = False
                                    tool_result_dict["stderr"] = res
                                else:
                                    tool_result_dict["stdout"] = res

                            elif tool_name == "write_file" and not task_completed:
                                new_content = args.get("content", "").strip()
                                if new_content.startswith("```"):
                                    lines = new_content.splitlines()[1:]
                                    if lines and lines[-1].strip() == "```":
                                        lines = lines[:-1]
                                    new_content = "\n".join(lines)
                                
                                content_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
                                file_content_sig = (norm_path, content_hash)
                                
                                if file_content_sig in content_signatures:
                                    print("REDUNDANT WRITE DETECTED:", norm_path)
                                    tool_result_dict["success"] = False
                                    tool_result_dict["stderr"] = f"Error: Redundant write payload. This content signature is already present on disk."
                                else:
                                    write_result = write_file(raw_path, new_content)
                                    if str(write_result).startswith("Error:"):
                                        tool_result_dict["success"] = False
                                        tool_result_dict["stderr"] = write_result
                                    else:
                                        content_signatures.add(file_content_sig)
                                        tool_result_dict["stdout"] = str(write_result)
                                        
                                        # ATOMIC REGISTRATION (Recorded instantly on disk write confirm)
                                        if norm_path:
                                            _written_files.add(norm_path)
                                        
                                        # Stateful High-Fidelity Verification Escape Check
                                        if expected_files and expected_files.issubset(_written_files):
                                            if not has_validation_commands or runtime_verified:
                                                console.print("[bold green]TASK COMPLETE VIA IMMEDIATE ESCAPE[/bold green]")
                                                response_content = "All required files created and verified successfully."
                                                task_completed = True
                                                break
                                            
                                        try:
                                            update_file_index(session, raw_path)
                                        except Exception as e:
                                            logger.warning(f"Index update skipped/failed for raw target {raw_path}: {e}")

                            elif tool_name == "replace_chunk":
                                target  = args.get("target_code", "")
                                replace = args.get("replacement_code", "").strip()
                                if replace.startswith("```"):
                                    lines = replace.splitlines()[1:]
                                    if lines and lines[-1].strip() == "```":
                                        lines = lines[:-1]
                                    replace = "\n".join(lines)
                                
                                content = read_file(raw_path)
                                if str(content).startswith("Error:"):
                                    tool_result_dict["success"] = False
                                    tool_result_dict["stderr"] = content
                                elif target in content:
                                    updated_content = content.replace(target, replace)
                                    
                                    content_hash = hashlib.sha256(updated_content.encode("utf-8")).hexdigest()
                                    file_content_sig = (norm_path, content_hash)
                                    
                                    if file_content_sig in content_signatures:
                                        tool_result_dict["success"] = False
                                        tool_result_dict["stderr"] = f"Error: Redundant chunk adjustment mutation. This resulting file configuration is already on disk."
                                    else:
                                        write_file(raw_path, updated_content)
                                        content_signatures.add(file_content_sig)
                                        tool_result_dict["stdout"] = "Chunk replaced successfully."
                                        
                                        if norm_path:
                                            _written_files.add(norm_path)
                                            
                                        if expected_files and expected_files.issubset(_written_files):
                                            if not has_validation_commands or runtime_verified:
                                                console.print("[bold green]TASK COMPLETE VIA IMMEDIATE ESCAPE[/bold green]")
                                                response_content = "All required files created and verified successfully."
                                                task_completed = True
                                                break
                                            
                                        try:
                                            update_file_index(session, raw_path)
                                        except Exception as e:
                                            logger.warning(f"Index update failed for raw target {raw_path}: {e}")
                                else:
                                    tool_result_dict["success"] = False
                                    tool_result_dict["stderr"] = "Error: target_code not found in file."

                            elif tool_name == "list_files":
                                tool_result_dict["stdout"] = list_files()

                            elif tool_name == "search_index":
                                tool_result_dict["stdout"] = str(search_index(session, args.get("query")))

                            elif tool_name == "install_package":
                                pkg = args.get("package", "").strip()
                                if not pkg:
                                    tool_result_dict["success"] = False
                                    tool_result_dict["stderr"] = "Error: No package name provided."
                                else:
                                    pip_pkg = _pip_name(pkg)
                                    if INSTALL_ATTEMPTS[pip_pkg] >= MAX_INSTALL_ATTEMPTS:
                                        tool_result_dict["success"] = False
                                        tool_result_dict["stderr"] = f"INSTALL LOCKOUT: Installation attempts for '{pip_pkg}' are forbidden."
                                    else:
                                        INSTALL_ATTEMPTS[pip_pkg] += 1
                                        confirm = input(f"Run 'pip install {pip_pkg}'? (y/n): ").lower()
                                        if confirm == "y":
                                            proc = subprocess.run(
                                                ["pip", "install", "--only-binary", ":all:", pip_pkg],
                                                capture_output=True, text=True
                                            )
                                            if proc.returncode == 0:
                                                out = (proc.stdout or "").strip()[-300:]
                                                console.print(f"[green]pip install {pip_pkg} done.[/green]")
                                                tool_result_dict["stdout"] = out or "Installed successfully."
                                            else:
                                                proc2 = subprocess.run(["pip", "install", pip_pkg], capture_output=True, text=True)
                                                out2 = (proc2.stdout or proc2.stderr or "").strip()[-400:]
                                                if proc2.returncode == 0:
                                                    tool_result_dict["stdout"] = out2 or "Installed."
                                                else:
                                                    tool_result_dict["success"] = False
                                                    tool_result_dict["stderr"] = (
                                                        f"Error: pip install {pip_pkg} failed.\n{out2}\n"
                                                        "CRITICAL AGENT NOTE: Installation failed. Do NOT attempt to run install again."
                                                    )
                                        else:
                                            tool_result_dict["success"] = False
                                            tool_result_dict["stderr"] = f"Install of '{pip_pkg}' aborted by user."

                            elif tool_name == "run_command":
                                cmd = args.get("command", "").strip()
                                
                                READ_ONLY_COMMANDS = ("git status", "git diff")
                                BUILD_TEST_COMMANDS = ("python ", "python3 ", "pytest ")
                                ALLOWED_INSTALLS = ("pip ",)
                                SERVER_FRAMEWORK_KEYWORDS = ["flask", "fastapi", "uvicorn", "streamlit", "app.py"]
                                
                                is_readable = any(cmd.startswith(p) for p in READ_ONLY_COMMANDS)
                                is_buildable = any(cmd.startswith(p) for p in BUILD_TEST_COMMANDS)
                                is_installable = any(cmd.startswith(p) for p in ALLOWED_INSTALLS)
                                is_server_process = any(keyword in cmd.lower() for keyword in SERVER_FRAMEWORK_KEYWORDS)
                                
                                if not (is_readable or is_buildable or is_installable):
                                    tool_result_dict["success"] = False
                                    tool_result_dict["stderr"] = f"Error: Command '{cmd}' rejected. Security policy violations."
                                else:
                                    confirm = "y" if is_readable else input(f"Execute '{cmd}'? (y/n): ").lower()
                                    if confirm == "y":
                                        # Non-blocking Validation Management via Popen() Strategy
                                        if is_server_process and is_buildable:
                                            console.print("[yellow]Long-running process / web-server detected. Applying Popen observation...[/yellow]")
                                            try:
                                                print("BEFORE RUN (SERVER POPEN SAFE-GUARD)")
                                                proc = subprocess.Popen(
                                                    cmd, shell=True,
                                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                    text=True, cwd=session.root
                                                )
                                                # Allow the process tree to stabilize for evaluation
                                                time.sleep(6)
                                                
                                                # Check if process is still running cleanly without exiting
                                                if proc.poll() is None:
                                                    print("AFTER RUN (OBSERVATION WINDOW STABLE)")
                                                    console.print("[green]State Machine Update: Background server successfully launched and remains active.[/green]")
                                                    tool_result_dict["success"] = True
                                                    tool_result_dict["stdout"] = "Application successfully started and maintained stability during observation."
                                                    runtime_verified = True
                                                    
                                                    # Graceful closure of verification process
                                                    proc.terminate()
                                                    proc.wait(timeout=3)
                                                else:
                                                    # Process crashed prematurely within the observation window
                                                    stdout, stderr = proc.communicate()
                                                    tool_result_dict["success"] = False
                                                    tool_result_dict["stderr"] = f"Process terminated prematurely during tracking.\nStdout:\n{stdout}\nStderr:\n{stderr}"
                                            except Exception as e:
                                                print("SERVER RUN ERROR:", repr(e))
                                                tool_result_dict["success"] = False
                                                tool_result_dict["stderr"] = f"Server failed to launch cleanly: {e}"
                                        else:
                                            print("BEFORE RUN")
                                            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=session.root)
                                            print("AFTER RUN")
                                            out = proc.stdout[-1000:] if proc.stdout else ""
                                            err = proc.stderr[-1000:] if proc.stderr else ""
                                            if proc.stdout and len(proc.stdout) > 1000: out = "...[TRUNCATED]\n" + out
                                            if proc.stderr and len(proc.stderr) > 1000: err = "...[TRUNCATED]\n" + err
                                            
                                            tool_result_dict["success"] = (proc.returncode == 0)
                                            tool_result_dict["stdout"] = out
                                            tool_result_dict["stderr"] = f"Exit code {proc.returncode}\n{err}"
                                            
                                            if proc.returncode == 0 and not is_readable:
                                                runtime_verified = True
                                                console.print("[green]State Machine Update: Execution/Verification command succeeded (exit code 0).[/green]")
                                        
                                        tool_result_dict = _try_auto_install(cmd, tool_result_dict)
                                    else:
                                        tool_result_dict["success"] = False
                                        tool_result_dict["stderr"] = "Command aborted by user."
                            elif tool_name == "print_message":
                                msg = args.get("message", "")
                                console.print(f"[bold green]Message:[/bold green] {msg}")
                                response_content = msg
                                task_completed = True
                                break
                            else:
                                tool_result_dict["success"] = False
                                tool_result_dict["stderr"] = f"Error: Unknown tool '{tool_name}'"

                        except Exception as e:
                            tool_result_dict["success"] = False
                            tool_result_dict["stderr"] = f"Tool Execution Error: {e}"

                        last_tool_metadata = {
                            "tool": tool_name,
                            "success": tool_result_dict["success"],
                            "path": raw_path if raw_path else args.get("command", "")
                        }

                        combined_result_str = json.dumps(tool_result_dict, indent=2)
                        console.print(f"[dim]Tool Result: {len(combined_result_str)} chars[/dim]")

                        # ── Multi-Tier Checklist Evaluation Gate ──
                        if tool_name in ("write_file", "replace_chunk", "run_command"):
                            print("DEBUG:", tool_name, "success=", tool_result_dict["success"], "path=", norm_path)
                            print("RAW PATH:", raw_path if raw_path else args.get("command", ""))
                            print("NORMALIZED:", repr(norm_path))
                            
                            files_complete = expected_files.issubset(_written_files)
                            
                            print("EXPECTED ARTIFACTS:", sorted(list(expected_files)))
                            print("WRITTEN ARTIFACTS :", sorted(list(_written_files)))
                            print("FILES COMPLETE    :", files_complete)
                            print("RUNTIME VERIFIED  :", runtime_verified)

                            if expected_files:
                                if files_complete and (not has_validation_commands or runtime_verified):
                                    console.print("[bold green]TASK COMPLETE: Blueprints generated and runtime behavior verified.[/bold green]")
                                    response_content = "All required application components created and script verifications executed successfully."
                                    task_completed = True
                                    break
                            else:
                                multi_file_heuristic = (
                                    " and " in user_input.lower()
                                    or "multiple" in user_input.lower()
                                    or "templates/" in user_input.lower()
                                )
                                if not multi_file_heuristic and tool_result_dict["success"]:
                                    if not has_validation_commands or runtime_verified:
                                        console.print("[bold green]TASK COMPLETE: Solitary blueprint execution complete.[/bold green]")
                                        response_content = "Solitary blueprint architecture modification and verification passed successfully."
                                        task_completed = True
                                        break

                            # ── Hard Runaway Loop Guard ──
                            if tool_name in ("write_file", "replace_chunk") and tool_result_dict["success"]:
                                duplicate_count[norm_path] += 1
                                if duplicate_count[norm_path] >= 2:
                                    console.print(f"[red]Duplicate artifact loop detected: {norm_path}[/red]")
                                    response_content = f"Created artifact {norm_path}. Stopped due to duplicate write loop."
                                    task_completed = True
                                    break

                        worker_history.append({"role": "assistant", "content": raw_response})
                        worker_history.append({
                            "role": "user",
                            "content": (
                                f"TOOL RESULT:\n{combined_result_str}\n\n"
                                "CRITICAL INSTRUCTION: When calling a tool, you must output ONLY valid raw JSON starting with '{'. "
                                "Do NOT explain, do NOT narrate steps, and do NOT write any markdown text outside the JSON block."
                            )
                        })

                        if not tool_result_dict["success"]:
                            worker_history.append({
                                "role": "user",
                                "content": (
                                    "The previous tool call failed. Do NOT explain the error or apologize. "
                                    "Respond with ONLY a corrected tool_call JSON starting with '{'."
                                )
                            })

                        tool_loops += 1
                        metrics.record_retry()
                        continue

                    elif resp_type == "response":
                        response_content = parsed_response.get("content", raw_response)
                        console.print()
                        console.print(response_content, style="green", markup=False, highlight=False)
                    else:
                        response_content = raw_response
                        if is_tool:
                            console.print()
                            console.print(response_content, style="green", markup=False, highlight=False)
                else:
                    response_content = raw_response
                    if is_tool:
                        console.print()
                        console.print(response_content, style="green", markup=False, highlight=False)

                if not response_content or not response_content.strip():
                    response_content = "[empty response from model]"

                if task_completed:
                    break

                # ── Critic Bypass Gate ────────────────────────────────────
                metrics.record_llm_call()
                critic = critique_response(
                    user_input=user_input,
                    response=response_content,
                    retrieval_used=bool(auto_context),
                    match_count=len(auto_context) if auto_context else 0,
                    context=full_context if full_context else "",
                    last_tool_name=last_tool_metadata["tool"] if last_tool_metadata else None,
                    last_tool_result=json.dumps(last_tool_metadata) if last_tool_metadata else None,
                )
                console.print(f"[blue]Critic Review (Pass {passes+1}):[/blue] ", end="")
                console.print(str(critic), markup=False, highlight=False)

                if "NEEDS_MORE_INFO" in critic:
                    passes += 1
                    metrics.record_retry()

                    if task.get("task_type") == "coding" and passes == 1:
                        console.print("[yellow]Critic flagged — auto-retrying once before asking.[/yellow]")
                        worker_history.append({"role": "assistant", "content": response_content})
                        worker_history.append({
                            "role": "user",
                            "content": "CRITIC FEEDBACK: Revise and continue. Use tool_call JSON only if more action is needed."
                        })
                        continue

                    if passes < max_passes:
                        console.print("[yellow]Critic flagged response. I am not fully sure.[/yellow]")
                        confirm = input("Proceed anyway? (y/n or clarification): ").strip()
                        if confirm.lower() == "y":
                            worker_history.append({"role": "assistant", "content": response_content})
                            worker_history.append({
                                "role": "user",
                                "content": "Proceed. Execute the corrected solution now using tool_call JSON only."
                            })
                            passes = 0
                            continue
                        elif confirm.lower() == "n":
                            console.print("[red]Aborted by user.[/red]")
                            response_content = "Aborted."
                            break
                        else:
                            console.print("[yellow]Asking worker to revise...[/yellow]")
                            worker_history.append({"role": "assistant", "content": response_content})
                            worker_history.append({
                                "role": "user",
                                "content": f"CRITIC FEEDBACK: Need more info. User clarification: {confirm}"
                            })
                    else:
                        console.print("[red]Response blocked by Critic after max passes.[/red]")
                        response_content = "I need more information to proceed. Please provide relevant files or logs."
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