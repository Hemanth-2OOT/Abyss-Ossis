# ABYSS OSSIS — Complete Guide (v1.0)

> A local-first, zero-cost AI coding agent powered by Qwen 2.5 Coder 7B.
> Works like Claude Code / Cursor — but runs entirely on your machine.
 
![status](https://img.shields.io/badge/status-active-brightgreen)
![license](https://img.shields.io/badge/license-MIT-blue)
---

## Table of Contents

1. [What is Abyss Ossis?](#what-is-abyss-ossis)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [How It Works (Execution Architecture)](#how-it-works-execution-architecture)
5. [All Commands](#all-commands)
6. [Autonomous Tool Calls](#autonomous-tool-calls)
7. [File Editing & Security](#file-editing--security)
8. [Project Memory](#project-memory)
9. [Project Isolation](#project-isolation)
10. [Codebase Structure](#codebase-structure)
11. [Troubleshooting](#troubleshooting)

---

## What is Abyss Ossis?

Abyss Ossis (LocalAgent) is a **project-attached coding runtime** — an AI agent that lives inside your project directory, understands your codebase through AST indexing and semantic search, and helps you read, write, edit, and debug code through a conversational terminal interface.

### Why it exists

| Commercial tools | Abyss Ossis |
|---|---|
| Claude Code costs $20+/month | **Free forever** |
| Sends your code to the cloud | **100% local, 100% private** |
| Requires internet | **Works fully offline** |
| Uses 200B+ parameter models | **Runs on Qwen 7B via Ollama** |

### What it can do

- **Understand your codebase** — AST-indexed + FAISS semantic search
- **Answer questions** — grounded in actual project files, not hallucinations
- **Edit files safely** — targeted replacement (`replace_chunk`), not full file rewrites
- **Run commands** — executes tests, scripts, and backgrounds long-running servers securely
- **Remember facts** — persistent per-project memory across sessions
- **Self-correct** — built-in retry exhaustion guard and JSON format recovery

---

## Installation

### Step 1: Install Ollama
Download from [https://ollama.com](https://ollama.com) and install it.

### Step 2: Pull the model
```bash
ollama pull qwen2.5-coder:7b
```

### Step 3: Install Python dependencies
```bash
cd local_agent
pip install -r requirements.txt
```

### Step 4: Start Ollama
Open a separate terminal and run `ollama serve`. Leave this running in the background.

---

## Quick Start

### Launch the agent on any project:
```bash
python cli.py run C:\path\to\your\project
```

On **first launch**, the agent automatically:
1. Scans all project files
2. Builds an AST index (functions, classes, imports)
3. Creates `.localagent.index.json`, `.localagent.memory.json`, `.localagent.logs.txt`

You can immediately start typing natural language requests.

---

## How It Works (Execution Architecture)

Abyss Ossis uses a highly deterministic, multi-phase execution loop designed to extract reliable tool usage from small (7B) local models.

```
┌─────────────────────────────────────────────────────────────┐
│                        YOU TYPE                             │
│               "run the backend and fix the UI"              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │     ORCHESTRATOR       │  Heuristic Task Classifier
              │  (task_type: execute)  │  Assigns capability profile
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   WORKER (EXECUTE)     │  Generates strictly JSON tools.
              │  (streams <think>      │  Injects real workspace context
              │   blocks securely)     │  so it doesn't hallucinate paths.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │    TOOL DISPATCHER     │  Executes tool logic securely.
              │  Records ToolEvents    │  Hard-aborts batch on unknown/
              │  to ExecutionState     │  illegal tools.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │ POST-TOOL VALIDATOR    │  Checks ExecutionState against
              │  (Did the task meet    │  declarative Task Contracts.
              │   its requirements?)   │  If not, auto-retries worker.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   WORKER (RESPOND)     │  Fed purely the factual transcript
              │  Generates final prose │  (files read, edited, commands).
              │  summary for the user. │  Zero hallucination.
              └────────────────────────┘
```

**Key Innovations:**
- **`ExecutionState`**: The single source of truth. Every executed tool records a `ToolEvent` (args, success status, output).
- **The 3-Layer Truth Model**: Execution cleanly separates OS truth (`returncode`), semantic completeness (`success = returncode == 0`), and runtime state (`status = "completed" | "running" | "failed"`). A server can be "running" but not semantically "completed" until explicitly verified.
- **`TaskContracts`**: A coding task isn't "complete" just because the LLM says `"type": "final"`. The validator checks `ExecutionState` to prove that a file was *actually* edited or a command explicitly returned code 0 before accepting completion.
- **`RESPOND` phase**: The final answer is generated completely isolated from the execution scratchpad, fed only factual, proven events.

---

## All Commands

### File Operations
| Command | What it does | Example |
|---|---|---|
| `/read <file>` | Read file contents (extracts ToolResult) | `/read src/app.py` |
| `/write <file> <text>` | Overwrite a file | `/write test.txt hello` |
| `/ls` | List all workspace files | `/ls` |
| `/edit <file> <inst>` | AI-powered edit with diff preview | `/edit utils.py add logging` |

### Index & Search
| Command | What it does |
|---|---|
| `/index` | Rebuild AST + FAISS index from scratch |
| `/showindex` | Display raw semantic index data |
| `/find <keyword>`| Search codebase for a symbol |

### Memory
| Command | What it does |
|---|---|
| `/remember <k> <v>`| Store a permanent fact (e.g. `/remember framework flask`) |
| `/forget <k>` | Delete a fact |
| `/memory` | Show all stored facts |

---

## Autonomous Tool Calls

When you use natural language, the agent routes to EXECUTE mode and may emit tools.

| Tool | Capability |
|---|---|
| `read_file` | Read files (cached to prevent duplicate reads) |
| `list_files` | Directory listing |
| `replace_chunk`| Targeted find-and-replace (line-exact replacement) |
| `run_command` | Execute tests or launch long-running servers securely |

### Hardened Tool Dispatcher:
- **Duplicate loop prevention**: If a model gets stuck calling the same tool with the exact same args 3 times, the system flags an infinite loop and forcibly halts.
- **Parse exhaustion**: If the LLM generates invalid JSON 3 times in a row, the pipeline cleanly aborts.
- **Batch invalidation**: If a model generates multiple tools in one turn, but includes an unknown or forbidden tool, execution of the entire batch stops immediately to prevent corrupted state.

---

## File Editing & Security

### `replace_chunk`
We never ask 7B models to rewrite 500-line files. `replace_chunk` uses exact string targeting to drop-in replacements seamlessly.

### `run_command`
A strict runtime policy handles bash execution:
1. `python <file>` is **only** permitted if `os.path.isfile(file)` returns true. The agent cannot hallucinate non-existent entry points.
2. Long-running frameworks (`flask`, `fastapi`, `uvicorn`, `npm start`) trigger a **6-second observation window**. The process is allowed to boot and stabilize. 
3. **Execution Semantics**: The system forces strict OS-level exit code validation. A process is only marked semantically `success=True` if it exits with `returncode == 0` or completes a successful long-running server boot. Semantic correctness is strictly decoupled from process liveness to prevent phantom execution loops.

---

## Project Memory & Isolation

### Memory Injection
Facts stored via `/remember` are dynamically injected into the system prompt at runtime. The LLM sees them on every pass. (Capped at 50 entries to prevent prompt bloat).

### Workspace Sandboxing
Each project directory has an isolated state:
```
my-project/
├── .localagent.index.json      ← AST / Semantic index
├── .localagent.memory.json     ← Memory facts
├── .localagent.logs.txt        ← Rolling log buffer
```
File resolution is strongly sandboxed to the project root. Path traversal (`../`) is intercepted and rejected by `core.sandbox`.

---

## Codebase Structure

```
local_agent/
├── cli.py                    # Multi-turn execution orchestrator
├── config.py                 # Hyperparameters (models, temp, budget)
│
├── core/
│   ├── orchestrator.py       # Adaptive routing & complexity scoring
│   ├── worker.py             # Context injection & Ollama execution
│   ├── execution_state.py    # Transactional state store (ToolEvents)
│   ├── post_tool_validator.py# Task Contract verification rules
│   ├── tool_result.py        # Abstract Tool Output standard
│   └── sandbox.py            # Path resolution & security locks
│
├── systems/
│   ├── ollama_client.py      # LLM stream parsing & connection
│   ├── memory.py             # Cross-session persistence
│   └── semantic_index.py     # Codebase FAISS querying
│
├── tools/
│   ├── replace_chunk.py      # Micro-editing engine
│   ├── run_command.py        # Safe runtime & observation bounds
│   └── code_indexer.py       # AST structure parsing
```

---

*Built with ❤️ for developers who want agentic AI without the cloud.*
