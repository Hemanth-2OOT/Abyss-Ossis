# ABYSS OSSIS — Complete Guide (v2.0)

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
8. [Project Memory & Sandboxing](#project-memory--sandboxing)
9. [Codebase Structure](#codebase-structure)

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

Abyss Ossis uses a highly deterministic, multi-phase execution loop designed to extract reliable tool usage from small (7B) local models without infinite looping or context collapse.

```text
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
              │       PLANNER          │  Breaks task into sequential
              │   (Generates JSON      │  Tool Requirements (R1, R2, R3).
              │   Execution Graph)     │  Avoids blind model guesswork.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   WORKER (EXECUTE)     │  Executes strictly defined tools.
              │  (Streams JSON tools   │  Maintains Context Memory of past
              │   within execution)    │  tool results to prevent amnesia.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │    TOOL DISPATCHER     │  Executes tool logic safely.
              │  Catches invalid tools │  Auto-heals missing modules via
              │  and injects feedback. │  automatic `pip install` detection.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │ POST-TOOL VALIDATOR    │  Tracks RequirementStatus state.
              │  (Did the task meet    │  Validates physical OS-level
              │   its requirements?)   │  changes. Blocks hallucinations.
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   WORKER (RESPOND)     │  Fed purely the proven factual
              │  Generates final prose │  transcript. Zero hallucination.
              │  summary for the user. │  
              └────────────────────────┘
```

**Key Innovations:**
- **Context Memory**: A core loop injection mechanism `worker_memory` tracks previous tool outputs. This fixes standard LLM "amnesia" and eliminates infinite loops where the LLM repeats previous actions blindly.
- **The 3-Layer Truth Model**: Execution cleanly separates OS truth (`returncode`), semantic completeness (`success = returncode == 0`), and runtime state (`status = "completed" | "running" | "failed"`). 
- **`TaskContracts` (`core/post_tool_validator.py`)**: A coding task isn't "complete" just because the LLM says `"type": "final"`. The validator checks `ExecutionState` to prove that a file was *actually* created or edited before marking the requirement Complete.
- **Auto-Healing Command Runner**: If a user request or internal test fails with a `ModuleNotFoundError`, the Tool Dispatcher automatically recognizes the missing dependency, alerts the user, and securely runs `pip install` before continuing.

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
| `write_file`| Secure creation of entirely new files |
| `list_files`| Directory listing |
| `replace_chunk`| Targeted find-and-replace using exact target strings |
| `run_command` | Execute tests or launch long-running servers securely |
| `delete_file` | File deletion with safety guards |

### Hardened Tool Security:
- **Duplicate loop prevention**: If a model gets stuck calling the same tool with the exact same args 3 times, the system flags an infinite loop and forcibly halts.
- **Parse exhaustion**: If the LLM generates invalid JSON 3 times in a row, the pipeline intercepts it and cleans the prompt.
- **Strict capability configs**: The system strictly enforces `max_reasoning_passes=5` and `max_tool_calls=15` to ensure small models stay focused and predictable.

---

## File Editing & Security

### `replace_chunk`
We never ask 7B models to rewrite 500-line files. `replace_chunk` uses exact string targeting (`target_code`, `replacement_code`) to drop-in replacements seamlessly. This completely eliminates context truncation.

### `run_command`
A strict runtime policy handles bash execution:
1. `python <file>` is **only** permitted if `os.path.isfile(file)` returns true. The agent cannot hallucinate non-existent entry points.
2. Long-running frameworks trigger an observation window allowing the process to boot and stabilize. 
3. **Execution Semantics**: The system forces strict OS-level exit code validation to prevent phantom execution loops.

---

## Project Memory & Sandboxing

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

```text
local_agent/
├── cli.py                        # Multi-turn execution orchestrator & Main Loop
├── config.py                     # Hyperparameters (models, temp, budget)
├── requirements.txt              # Project dependencies (FAISS, Rich, etc.)
│
├── core/
│   ├── critic.py                 # Evaluates outputs and detects hallucinations
│   ├── execution_state.py        # Transactional state store (ToolEvents)
│   ├── guards.py                 # Safety constraints and input validation
│   ├── metrics.py                # Tracks reasoning passes and tool limits
│   ├── orchestrator.py           # Adaptive routing & complexity scoring
│   ├── planner.py                # Generates execution graphs to prevent guessing
│   ├── post_tool_validator.py    # Task Contract verification rules
│   ├── resource_monitor.py       # Watchdog for resource thresholds
│   ├── sandbox.py                # Path resolution & security locks
│   ├── tool_dispatcher.py        # Safely calls tool modules based on LLM JSON
│   ├── tool_registry.py          # Strict tool capability schemas
│   ├── tool_result.py            # Abstract Tool Output standard
│   └── worker.py                 # ReAct execution loop & Context memory injection
│
├── systems/
│   ├── memory.py                 # Cross-session conversational persistence
│   ├── ollama_client.py          # LLM stream parsing & connection
│   └── semantic_index.py         # Codebase FAISS querying
│
├── tools/
│   ├── code_indexer.py           # AST structure parsing
│   ├── context_builder.py        # Assembles prompt context for the LLM
│   ├── delete_file.py            # Secure file deletion
│   ├── directory_reader.py       # Workspace discovery
│   ├── file_reader.py            # Safe read buffers
│   ├── file_writer.py            # Creates new files
│   ├── index_storage.py          # Serializes semantic indices to disk
│   ├── replace_chunk.py          # Micro-editing engine (find-and-replace)
│   └── run_command.py            # Safe runtime & observation bounds
```

---

*Built with ❤️ for developers who want agentic AI without the cloud.*
