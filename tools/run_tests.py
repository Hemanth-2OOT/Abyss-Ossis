import subprocess
import shlex
from core.sandbox import sandbox
from core.logger import get_logger

logger = get_logger(__name__)

ALLOWED_TEST_COMMANDS = [
    "pytest",
    "python -m unittest",
    "npm test"
]

def run_tests(command="pytest"):
    if not any(command.startswith(allowed) for allowed in ALLOWED_TEST_COMMANDS):
        return f"Error: Command '{command}' is not allowed. Allowed commands: {', '.join(ALLOWED_TEST_COMMANDS)}"
        
    try:
        safe_cwd = sandbox.workspace_root
        args = shlex.split(command)
        
        process = subprocess.run(
            args, 
            cwd=safe_cwd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            timeout=60
        )
        
        output = process.stdout
        
        if len(output) > 4000:
            output = output[:2000] + "\n...[TRUNCATED]...\n" + output[-2000:]
            
        status = "PASSED" if process.returncode == 0 else "FAILED"
        
        return f"Test Run {status}\n\nOutput:\n{output}"
        
    except subprocess.TimeoutExpired:
        return "Error: Test run timed out after 60 seconds."
    except Exception as e:
        logger.error(f"Failed to run test command '{command}': {e}", exc_info=True)
        return f"Error: {e}"
