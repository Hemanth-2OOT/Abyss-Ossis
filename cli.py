import os
print("CWD:", os.getcwd())
from rich.console import Console
from core.logger import get_logger
from systems.state import AgentState
from core.orchestrator import classify_task
from core.worker import run_worker
from core.critic import critique_response
from core.guards import requires_more_info

from tools.file_reader import read_file
from tools.file_writer import write_file
from tools.directory_reader import list_files
from core.tool_router import detect_tool
from tools.code_indexer import build_index
from tools.index_storage import save_index, load_index, search_index
from tools.context_builder import build_context
from tools.edit_utils import build_edit_prompt 
from tools.diff_viewer import show_diff
from systems.semantic_index import sync_faiss_with_ast

console = Console()
state = AgentState()
logger = get_logger("cli")

# Main function to handle user interactions and process tasks
from core.session import ProjectSession

def main(session):
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
    console.print(f"  [dim]Local AI Coding Agent · Qwen 2.5 Coder 7B · Ollama[/dim]")
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

            # 1. COMMANDS (Highest Priority)
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
                sync_faiss_with_ast()
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

            if user_input.startswith("/read"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    console.print("[red]Usage: /read <filename>[/red]")
                    continue
                console.print(read_file(parts[1]), markup=False)
                continue
            
            if user_input.startswith("/write"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[red]Usage: /write <filename> <content>[/red]")
                    continue
                path, content = parts[1], parts[2]
                
                # FIX: Convert literal "\n" strings into real newlines for terminal compatibility
                content = content.replace("\\n", "\n")
                
                result = write_file(path, content)
                console.print(result, style="green", markup=False)
                continue

            if user_input.startswith("/edit"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 3:
                    console.print("[red]Usage: /edit <file> <instruction>[/red]")
                    continue
                
                path, instruction = parts[1], parts[2]
                
                # Get current state for diffing
                old_code = read_file(path)
                
                # Generate new code
                prompt = build_edit_prompt(path, instruction)
                edited_code = run_worker(
                    session,
                    {"task_type": "editing"},
                    [{"role": "user", "content": prompt}],
                    None
                )

                # Remove markdown fences if model adds them
                edited_code = edited_code.strip()
                if edited_code.startswith("```"):
                    lines = edited_code.splitlines()
                    lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    edited_code = "\n".join(lines)

                # Display diff and confirm
                diff = show_diff(old_code, edited_code)
                console.print("\n[cyan]Proposed Changes:[/cyan]")
                console.print(diff, markup=False)

                confirm = input("\nApply changes? (y/n): ").lower()
                if confirm == "y":
                    write_file(path, edited_code)
                    console.print("[green]File updated.[/green]")
                else:
                    console.print("[yellow]Edit cancelled.[/yellow]")
                continue

            # 2. TOOL AUTO-DETECTION
            tool = detect_tool(user_input)
            if tool:
                console.print(f"[dim]Tool detected: {tool['tool']}[/dim]")
                if tool["tool"] == "ls":
                    console.print(list_files(), style="cyan", markup=False)
                elif tool["tool"] == "read":
                    console.print(read_file(tool["path"]), markup=False)
                continue

            # 3. AGENT PIPELINE
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
                plan_steps = generate_plan(user_input, full_context)
                console.print("\n[bold cyan]Execution Plan:[/bold cyan]")
                for i, step in enumerate(plan_steps, 1):
                    console.print(f"  {i}. ", style="cyan", end="")
                    console.print(str(step), markup=False)
                
                plan_str = "Execution Plan:\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(plan_steps, 1))
                if full_context:
                    full_context += "\n\n" + plan_str
                else:
                    full_context = plan_str

            state.add_message("user", user_input)
            
            max_passes = 2
            passes = 0
            worker_history = list(state.messages)
            
            max_tool_loops = 2
            tool_loops = 0
            
            while passes < max_passes and tool_loops <= max_tool_loops:
                response_stream = run_worker(session, task, worker_history, full_context, stream=True)
                
                raw_response = ""
                is_tool = None
                
                for chunk in response_stream:
                    raw_response += chunk
                    if is_tool is None:
                        stripped = raw_response.lstrip()
                        if len(stripped) > 0:
                            if stripped.startswith("{"):
                                is_tool = True
                            else:
                                is_tool = False
                                console.print("\n[green]", end="")
                                console.print(chunk, end="", flush=True)
                    elif not is_tool:
                        console.print(chunk, end="", flush=True)
                
                if not is_tool:
                    console.print("[/green]\n")
                
                # Parse JSON
                parsed_response = None
                if is_tool:
                    try:
                        import json
                        text = raw_response.strip()
                        if text.startswith("```json"): text = text[7:]
                        elif text.startswith("```"): text = text[3:]
                        if text.endswith("```"): text = text[:-3]
                        parsed_response = json.loads(text.strip())
                    except Exception:
                        pass
                
                if parsed_response and isinstance(parsed_response, dict):
                    resp_type = parsed_response.get("type")
                    if resp_type == "tool_call" and tool_loops < max_tool_loops:
                        tool_name = parsed_response.get("tool")
                        args = parsed_response.get("args", {})
                        console.print(f"\n[magenta]Tool Call:[/magenta] {tool_name}({args})")
                        session.log(f"TOOL: {tool_name}({args})")
                        
                        tool_result = ""
                        try:
                            if tool_name == "read_file":
                                tool_result = read_file(args.get("path"))
                            elif tool_name == "replace_chunk":
                                path = args.get("path")
                                target = args.get("target_code", "")
                                replace = args.get("replacement_code", "")
                                
                                # Output Guard: Strip markdown from replacement
                                replace = replace.strip()
                                if replace.startswith("```"):
                                    lines = replace.splitlines()[1:]
                                    if lines and lines[-1].strip() == "```": lines = lines[:-1]
                                    replace = "\n".join(lines)
                                
                                content = read_file(path)
                                if target in content:
                                    content = content.replace(target, replace)
                                    write_file(path, content)
                                    tool_result = "Chunk replaced successfully."
                                else:
                                    tool_result = "Error: target_code not found in file."
                            elif tool_name == "list_files":
                                tool_result = list_files()
                            elif tool_name == "search_index":
                                tool_result = str(search_index(session, args.get("query")))
                            elif tool_name == "run_command":
                                cmd = args.get("command")
                                confirm = input(f"Execute '{cmd}'? (y/n): ").lower()
                                if confirm == 'y':
                                    import subprocess
                                    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=session.root)
                                    out = proc.stdout[-1000:] if proc.stdout else ""
                                    err = proc.stderr[-1000:] if proc.stderr else ""
                                    if proc.stdout and len(proc.stdout) > 1000: out = "...[TRUNCATED]\n" + out
                                    if proc.stderr and len(proc.stderr) > 1000: err = "...[TRUNCATED]\n" + err
                                    tool_result = f"Exit code {proc.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
                                else:
                                    tool_result = "Command aborted by user."
                            else:
                                tool_result = f"Error: Unknown tool '{tool_name}'"
                        except Exception as e:
                            tool_result = f"Tool Execution Error: {e}"
                        
                        console.print(f"[dim]Tool Result: {len(str(tool_result))} chars[/dim]")
                        worker_history.append({"role": "assistant", "content": raw_response})
                        worker_history.append({"role": "user", "content": f"TOOL RESULT:\n{tool_result}"})
                        tool_loops += 1
                        continue
                    
                    elif resp_type == "response":
                        response_content = parsed_response.get("content", raw_response)
                        console.print(f"\n[green]{response_content}[/green]")
                    else:
                        response_content = raw_response
                        if is_tool: console.print(f"\n[green]{response_content}[/green]")
                else:
                    response_content = raw_response
                    if is_tool: console.print(f"\n[green]{response_content}[/green]")
                
                critic = critique_response(
                    user_input=user_input,
                    response=response_content,
                    retrieval_used=bool(auto_context),
                    match_count=len(auto_context) if auto_context else 0,
                    context=full_context if full_context else ""
                )
                console.print(f"[blue]Critic Review (Pass {passes+1}): {critic}[/blue]")
                
                if "NEEDS_MORE_INFO" in critic:
                    passes += 1
                    if passes < max_passes:
                        console.print("[yellow]Critic flagged response. I am not fully sure.[/yellow]")
                        confirm = input("Proceed anyway? (y/n or clarification): ").strip()
                        if confirm.lower() == 'y':
                            break
                        elif confirm.lower() == 'n':
                            console.print("[red]Aborted by user.[/red]")
                            response_content = "Aborted."
                            break
                        else:
                            console.print("[yellow]Asking worker to revise based on input...[/yellow]")
                            worker_history.append({"role": "assistant", "content": response_content})
                            worker_history.append({
                                "role": "user", 
                                "content": f"CRITIC FEEDBACK: You need more info. User clarification: {confirm}"
                            })
                    else:
                        console.print("[red]Response blocked by Critic after max passes.[/red]")
                        response_content = "I need more information to proceed. Please provide relevant files or logs."
                        break
                else:
                    break

            # Only save the final cleaned response to global state
            session.log(f"AGENT: {response_content}")
            state.add_message("assistant", response_content)

        except RuntimeError as e:
            console.print(f"[bold yellow]Agent Error:[/bold yellow] {e}")
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            break
        except Exception as e:
            logger.critical(f"Unexpected error: {e}", exc_info=True)
            console.print(f"[bold red]Unexpected Error:[/bold red] {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        console.print("[red]Usage: python cli.py run <project_path>[/red]")
        sys.exit(1)
        
    project_path = sys.argv[2]
    session = ProjectSession(project_path)
    
    # Auto project bootstrap
    if not os.path.exists(session.index_path):
        console.print("[yellow]Project not indexed. Initializing...[/yellow]")
        from tools.code_indexer import build_index
        import json
        index = build_index(session.root)
        with open(session.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        session.log("Project initialized")
        console.print("[green]Initialization complete.[/green]")

    main(session)