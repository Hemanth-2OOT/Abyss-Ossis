import time
try:
    import psutil
except ImportError:
    psutil = None

class MetricsTracker:
    def __init__(self, max_reasoning_passes: int = 3, max_tool_calls: int = 12):
        self.max_reasoning_passes = max_reasoning_passes
        self.max_tool_calls = max_tool_calls
        self.start_time = time.time()
        self.start_cpu = time.process_time()
        
        self.reasoning_passes = 0
        self.tool_calls = 0
        self.llm_calls = 0
        self.parse_retries = 0
        self.validation_retries = 0
        self.tool_hallucination_retries = 0
        self.planner_regenerations = 0
        self.resource_failures = 0
        
        self.planner_time = 0.0
        self.worker_time = 0.0
        self.tool_time = 0.0
        self.validation_time = 0.0
        
        # Tools executed
        self.observability_history_log = []
        
        # Determine initial memory
        if psutil:
            self.process = psutil.Process()
            self.peak_memory = self.process.memory_info().rss
        else:
            self.process = None
            self.peak_memory = 0
        
    def record_llm_call(self):
        self.llm_calls += 1
        
    def record_retry(self):
        self.reasoning_passes += 1
        

        
    def update_peak_memory(self):
        if self.process:
            current_mem = self.process.memory_info().rss
            if current_mem > self.peak_memory:
                self.peak_memory = current_mem

    def finish_task(self, context_size: int = 0) -> str:
        self.update_peak_memory()
        elapsed_time = time.time() - self.start_time
        cpu_time = time.process_time() - self.start_cpu
        mem_mb = self.peak_memory / (1024 * 1024)
        
        lines = [
            "\n[bold cyan]─── turn execution metrics ───[/bold cyan]",
            f"  [bold white]Reasoning Passes:[/bold white] {self.reasoning_passes}/{self.max_reasoning_passes}",
            f"  [bold white]Tool Calls:[/bold white]       {self.tool_calls}/{self.max_tool_calls}",
            f"  [bold white]Planner Retries:[/bold white]  {self.planner_regenerations}",
            f"  [bold white]Parse Retries:[/bold white]    {self.parse_retries}",
            f"  [bold white]Validation Fails:[/bold white] {self.validation_retries}",
            f"  [bold white]LLM API Calls:[/bold white]    {self.llm_calls}",
            f"  [bold white]Prompt/Context:[/bold white]   ~{context_size} chars",
            f"  [bold white]Tools Triggered:[/bold white]  {', '.join(self.observability_history_log) if self.observability_history_log else 'none'}",
            f"  [bold white]Peak CPU Time:[/bold white]    {cpu_time:.2f} s",
            f"  [bold white]Peak Memory:[/bold white]      ~{mem_mb:.1f} MB",
            f"  [bold white]Elapsed Time:[/bold white]    {elapsed_time:.2f} s"
        ]
        if self.resource_failures > 0:
            lines.append(f"  [bold red]Resource Failures:[/bold red]  {self.resource_failures}")
        lines.append("[bold cyan]─────────────────────────────────────[/bold cyan]\n")
        return "\n".join(lines)
