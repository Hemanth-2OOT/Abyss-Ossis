import os
import subprocess
import time
from core.tool_result import ToolResult

def _cleanup_proc(proc: subprocess.Popen):
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        
def run_command(cmd: str, cwd: str, timeout: int = 30) -> ToolResult:
    """
    Executes a shell command securely and safely, returning a ToolResult.

    Security policy:
    - Read-only commands (git status/diff) are always allowed.
    - Package installs (pip, npm install) are always allowed.
    - Python/pytest commands are allowed.
    - Server-framework keywords (flask, uvicorn, etc.) trigger long-running mode.
    - `python <file>` commands are allowed only if that file actually exists on disk.
    - All other commands are rejected.

    Long-running server/framework commands use a 6-second observation window
    then are cleanly terminated if stable, to prevent blocking.
    """
    cmd = cmd.strip()

    # ── Security & Lifecycle Triage ──────────────────────────────────────────
    READ_ONLY_COMMANDS    = ("git status", "git diff")
    BUILD_TEST_PREFIXES   = ("python ", "python3 ", "pytest ", "npm test", "npm run")
    ALLOWED_INSTALL_PREFIXES = ("pip ", "npm install")
    SERVER_FRAMEWORK_KEYWORDS = [
        "flask", "fastapi", "uvicorn", "streamlit", "npm start", "npm run dev",
    ]

    is_readable    = any(cmd.startswith(p) for p in READ_ONLY_COMMANDS)
    is_installable = any(cmd.startswith(p) for p in ALLOWED_INSTALL_PREFIXES)
    is_test        = any(cmd.startswith(p) for p in BUILD_TEST_PREFIXES)
    is_server_keyword = any(k in cmd.lower() for k in SERVER_FRAMEWORK_KEYWORDS)

    # For `python <file.py>` commands: allow only if the target file exists
    is_python_with_existing_file = False
    if cmd.startswith("python ") or cmd.startswith("python3 "):
        parts = cmd.split()
        if len(parts) >= 2:
            candidate = parts[1]
            candidate_path = os.path.join(cwd, candidate) if not os.path.isabs(candidate) else candidate
            if os.path.isfile(candidate_path):
                is_python_with_existing_file = True
            else:
                return ToolResult(
                    success=False,
                    stdout="",
                    stderr=(
                        f"Error: File '{candidate}' does not exist in the workspace. "
                        f"Use list_files to discover available Python files before running."
                    ),
                    summary=f"Rejected: '{candidate}' not found on disk."
                )

    is_allowed = (
        is_readable
        or is_installable
        or is_test
        or is_server_keyword
        or is_python_with_existing_file
    )

    if not is_allowed:
        return ToolResult(
            success=False,
            stdout="",
            stderr=f"Error: Command '{cmd}' rejected by security policy.",
            summary="Command rejected by policy."
        )

    # ── Long Running Observation Window (servers/frameworks) ─────────────────
    if is_server_keyword or is_python_with_existing_file:
        try:
            proc = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=cwd
            )
            time.sleep(6)

            is_server_mode = (proc.poll() is None)
            
            if is_server_mode:
                _cleanup_proc(proc)
                stdout, stderr = proc.communicate()
                
                if proc.stdout: proc.stdout.close()
                if proc.stderr: proc.stderr.close()
                
                return ToolResult(
                    success=True,
                    is_long_running=True,
                    status="running",
                    stdout=stdout,
                    stderr=stderr,
                    summary="Process started successfully and remained alive during observation window (status: running)."
                )
            else:
                stdout, stderr = proc.communicate()
                
                if proc.stdout: proc.stdout.close()
                if proc.stderr: proc.stderr.close()
                
                success = (proc.returncode == 0)
                status = "completed" if success else "failed"
                return ToolResult(
                    success=success,
                    status=status,
                    stdout=stdout,
                    stderr=f"Exit code {proc.returncode}\n{stderr}" if not success else stderr,
                    summary=f"Process exited early with code {proc.returncode} (status: {status})"
                )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            return ToolResult(
                success=False,
                status="failed",
                stdout="",
                stderr=f"Server failed to launch cleanly: {e}",
                summary="Exception during server launch."
            )

    # ── Short Running Synchronous Command ─────────────────────────────────────
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd, timeout=timeout
        )
        out = proc.stdout[-2000:] if proc.stdout else ""
        err = proc.stderr[-2000:] if proc.stderr else ""
        if proc.stdout and len(proc.stdout) > 2000:
            out = "...[TRUNCATED]\n" + out
        if proc.stderr and len(proc.stderr) > 2000:
            err = "...[TRUNCATED]\n" + err

        success = (proc.returncode == 0)
        return ToolResult(
            success=success,
            stdout=out,
            stderr=f"Exit code {proc.returncode}\n{err}" if not success else err,
            runtime_verified=success and not is_readable,
            summary=f"Command exited with code {proc.returncode}"
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds.",
            summary="Command timeout."
        )
    except KeyboardInterrupt:
        raise
    except Exception as e:
        return ToolResult(
            success=False,
            status="failed",
            stdout="",
            stderr=f"Exception executing command: {e}",
            summary="Execution exception."
        )
