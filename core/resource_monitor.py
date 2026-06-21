import os
import time
import threading
import psutil
from collections import deque
from config import MODEL_MEMORY_REQUIREMENTS, WARNING_RAM_PERCENT, MAX_RAM_PERCENT, MIN_AVAILABLE_VRAM_MB
from core.logger import get_logger
from rich.console import Console

console = Console()
logger = get_logger(__name__)

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

class ResourceSafetyError(Exception):
    def __init__(self, message, current_ram_gb=None, required_ram_gb=None):
        super().__init__(message)
        self.message = message
        self.current_ram_gb = current_ram_gb
        self.required_ram_gb = required_ram_gb

    def __str__(self):
        msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"[bold red]RESOURCE SAFETY LIMIT REACHED[/bold red]\n\n"
        )
        if self.current_ram_gb is not None and self.required_ram_gb is not None:
            msg += (
                f"Available RAM:\n"
                f"{self.current_ram_gb:.1f} GB\n\n"
                f"Required:\n"
                f"{self.required_ram_gb:.1f} GB\n\n"
            )
        msg += (
            f"Operation cancelled.\n\n"
            f"Suggestions:\n"
            f"• Close Chrome\n"
            f"• Close VS Code terminals\n"
            f"• Unload Ollama models\n"
            f"• Restart Ollama\n"
            f"• Use qwen2.5-coder:7b\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        return msg

class Watchdog:
    def __init__(self):
        self.cancel_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = None
        
        self.history_size = 120  # 60s at 500ms intervals
        self.history_ram = deque(maxlen=self.history_size)
        self.history_cpu = deque(maxlen=self.history_size)
        self.history_swap = deque(maxlen=self.history_size)
        self.history_vram = deque(maxlen=self.history_size)
        
        self.current_ollama_ram_mb = 0
        self.current_python_ram_mb = 0
        self.largest_child_name = ""
        self.largest_child_ram_mb = 0
        
        self.required_ram_gb = 1.0
        
        # Initialize CPU percent
        psutil.cpu_percent(interval=None)
        self.agent_process = psutil.Process()

    def set_required_model(self, model_name):
        self.required_ram_gb = MODEL_MEMORY_REQUIREMENTS.get(model_name, 2.0) + 1.0  # +1GB safety buffer

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def check(self):
        if self.cancel_event.is_set():
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            raise ResourceSafetyError("Resource usage exceeded safety limits.", available_gb, self.required_ram_gb)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as e:
                logger.error(f"Watchdog polling error: {e}")
            time.sleep(0.5)

    def _poll(self):
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=None)
        
        ram_percent = mem.percent
        swap_percent = swap.percent
        available_gb = mem.available / (1024 ** 3)
        disk_free_gb = psutil.disk_usage('/').free / (1024 ** 3)
        
        vram_percent = 0.0
        if HAS_GPUTIL:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    vram_percent = (gpu.memoryUsed / gpu.memoryTotal) * 100
                    # Check strict VRAM available
                    if gpu.memoryFree < MIN_AVAILABLE_VRAM_MB:
                        self._trigger_cancellation()
            except Exception:
                pass
                
        # Record history
        self.history_ram.append(ram_percent)
        self.history_cpu.append(cpu)
        self.history_swap.append(swap_percent)
        self.history_vram.append(vram_percent)

        # Track processes safely
        self._track_processes()

        # Check critical limits
        if ram_percent >= MAX_RAM_PERCENT or available_gb < self.required_ram_gb or swap_percent > 90.0 or disk_free_gb < 2.0:
            self._trigger_cancellation()

    def _track_processes(self):
        self.current_python_ram_mb = self.agent_process.memory_info().rss / (1024 * 1024)
        
        max_child_ram = 0
        max_child_name = ""
        
        try:
            children = self.agent_process.children(recursive=True)
            for child in children:
                try:
                    c_mem = child.memory_info().rss / (1024 * 1024)
                    if c_mem > max_child_ram:
                        max_child_ram = c_mem
                        max_child_name = child.name()
                except psutil.NoSuchProcess:
                    pass
        except Exception:
            pass
            
        self.largest_child_ram_mb = max_child_ram
        self.largest_child_name = max_child_name

        ollama_ram = 0
        try:
            for proc in psutil.process_iter(['name', 'memory_info']):
                if proc.info['name'] and proc.info['name'].lower().startswith('ollama'):
                    ollama_ram += proc.info['memory_info'].rss / (1024 * 1024)
        except Exception:
            pass
        self.current_ollama_ram_mb = ollama_ram

    def _trigger_cancellation(self):
        if not self.cancel_event.is_set():
            # Gracefully kill children
            try:
                children = self.agent_process.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                
                # Wait up to 5 seconds
                gone, alive = psutil.wait_procs(children, timeout=5.0)
                
                # Force kill survivors
                for child in alive:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
            except Exception:
                pass
                
            self.cancel_event.set()

    def wait_for_cooldown(self):
        """Blocks until system resources are stable for 5 consecutive seconds."""
        if not self.cancel_event.is_set():
            return
            
        console.print("[yellow]System cooling down...[/yellow]")
        stable_seconds = 0
        
        while stable_seconds < 5:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            if mem.percent < WARNING_RAM_PERCENT and swap.percent < 50.0:
                stable_seconds += 1
            else:
                stable_seconds = 0
                
            time.sleep(1.0)
            
        self.cancel_event.clear()
        console.print("[green]System stabilized. Continuing.[/green]")

    def health(self):
        """Returns a formatted diagnostic dashboard string."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=None)
        disk = psutil.disk_usage('/')
        
        peak_ram = max(self.history_ram) if self.history_ram else mem.percent
        peak_cpu = max(self.history_cpu) if self.history_cpu else cpu
        peak_swap = max(self.history_swap) if self.history_swap else swap.percent
        peak_vram = max(self.history_vram) if self.history_vram else 0.0
        
        total_ram_gb = mem.total / (1024 ** 3)
        used_ram_gb = (mem.total - mem.available) / (1024 ** 3)
        disk_free_gb = disk.free / (1024 ** 3)
        
        import requests
        loaded_models = []
        try:
            res = requests.get("http://localhost:11434/api/ps", timeout=2)
            loaded_models = [m["name"] for m in res.json().get("models", [])]
        except Exception:
            loaded_models = ["Unknown (Ollama offline/unreachable)"]

        # Model Recommendations
        recommendations = []
        for model, req in MODEL_MEMORY_REQUIREMENTS.items():
            if mem.available / (1024 ** 3) >= (req + 1.0):
                recommendations.append(f"[green]✓ {model}[/green]")
            else:
                deficit = (req + 1.0) - (mem.available / (1024 ** 3))
                recommendations.append(f"[red]✗ {model} (needs +{deficit:.1f}GB)[/red]")

        status = "[green]✓ Healthy[/green]" if not self.cancel_event.is_set() else "[red]✗ Cancelled (Cooling down)[/red]"

        msg = (
            f"\n[bold cyan]System Health[/bold cyan]\n"
            f"──────────────\n\n"
            f"[bold]RAM:[/bold]\n  {used_ram_gb:.1f} / {total_ram_gb:.1f} GB\n\n"
            f"[bold]Swap:[/bold]\n  {swap.percent}%\n\n"
            f"[bold]CPU:[/bold]\n  {cpu}%\n\n"
        )
        if HAS_GPUTIL:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    msg += f"[bold]GPU VRAM:[/bold]\n  {g.memoryUsed/1024:.1f} / {g.memoryTotal/1024:.1f} GB\n\n"
            except Exception:
                pass
                
        msg += (
            f"[bold]Disk Free:[/bold]\n  {disk_free_gb:.1f} GB\n\n"
            f"[bold]Last 60s Peaks:[/bold]\n  RAM: {peak_ram:.1f}% | CPU: {peak_cpu:.1f}% | Swap: {peak_swap:.1f}% | VRAM: {peak_vram:.1f}%\n\n"
            f"[bold]Processes:[/bold]\n"
            f"  Python: {self.current_python_ram_mb:.1f} MB\n"
            f"  Ollama: {self.current_ollama_ram_mb:.1f} MB\n"
        )
        if self.largest_child_name:
            msg += f"  Largest Child: {self.largest_child_name} ({self.largest_child_ram_mb:.1f} MB)\n"
            
        msg += (
            f"\n[bold]Loaded Ollama Models:[/bold]\n  {', '.join(loaded_models) if loaded_models else 'None'}\n\n"
            f"[bold]Model Recommendations:[/bold]\n  " + "\n  ".join(recommendations) + "\n\n"
            f"[bold]Status:[/bold]\n  {status}\n"
        )
        return msg

# Global singleton
watchdog = Watchdog()
