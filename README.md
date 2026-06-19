# ABYSS OSSIS — Complete Guide

> A local-first, zero-cost AI coding agent powered by Qwen 2.5 Coder 7B.
> Works like Claude Code / Cursor — but runs entirely on your machine.
 
![status](https://img.shields.io/badge/status-active-brightgreen)
![license](https://img.shields.io/badge/license-MIT-blue)
---

## Table of Contents

1. [What is Abyss Ossis?](#what-is-abyss-ossis)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [How It Works](#how-it-works)
5. [All Commands](#all-commands)
6. [Agent Mode (Natural Language)](#agent-mode)
7. [Autonomous Tool Calls](#autonomous-tool-calls)
8. [File Editing](#file-editing)
9. [Project Memory](#project-memory)
10. [Project Isolation](#project-isolation)
11. [Storage & Limits](#storage--limits)
12. [Architecture](#architecture)
13. [Configuration](#configuration)
14. [Troubleshooting](#troubleshooting)
15. [Tips for Best Results](#tips-for-best-results)

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
- **Edit files safely** — patch-based targeted edits, not full file rewrites
- **Run commands** — with explicit user approval (y/n)
- **Remember facts** — persistent per-project memory across sessions
- **Stream responses** — real-time token output like Claude Code
- **Self-correct** — built-in critic loop that validates responses

---

## Installation

### Step 1: Install Ollama

Download from [https://ollama.com](https://ollama.com) and install it.

### Step 2: Pull the model

```bash
ollama pull qwen2.5-coder:7b
```

### Step 3: Clone / locate the agent

```
C:\Users\HEMANTH\Desktop\local_agent\
```

### Step 4: Install Python dependencies

```bash
cd C:\Users\HEMANTH\Desktop\local_agent
pip install -r requirements.txt
```

The dependencies are minimal:
```
requests    — HTTP client for Ollama API
numpy       — numerical operations for FAISS
rich        — terminal formatting and colors
faiss-cpu   — semantic vector search
```

### Step 5: Start Ollama

Open a separate terminal and run:
```bash
ollama serve
```

Leave this running in the background.

---

## Quick Start

### Launch the agent on any project:

```bash
python cli.py run C:\path\to\your\project
```

### Example:

```bash
python cli.py run C:\projects\my-flask-app
```

### What you will see:

```
    ╔══════════════════════════════════════════════════════════════════╗
    ║     █████╗ ██████╗ ██╗   ██╗███████╗███████╗                   ║
    ║    ██╔══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██╔════╝                   ║
    ║    ███████║██████╔╝ ╚████╔╝ ███████╗███████╗                   ║
    ║    ██╔══██║██╔══██╗  ╚██╔╝  ╚════██║╚════██║                   ║
    ║    ██║  ██║██████╔╝   ██║   ███████║███████║                   ║
    ║    ╚═╝  ╚═╝╚═════╝    ╚═╝   ╚══════╝╚══════╝                   ║
    ║      ██████╗ ███████╗███████╗██╗███████╗                       ║
    ║     ██╔═══██╗██╔════╝██╔════╝██║██╔════╝                       ║
    ║     ██║   ██║███████╗███████╗██║███████╗                       ║
    ║     ██║   ██║╚════██║╚════██║██║╚════██║                       ║
    ║     ╚██████╔╝███████║███████║██║███████║                       ║
    ║      ╚═════╝ ╚══════╝╚══════╝╚═╝╚══════╝                       ║
    ╚══════════════════════════════════════════════════════════════════╝

  Local AI Coding Agent · Qwen 2.5 Coder 7B · Ollama
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Workspace:  C:\projects\my-flask-app
  Memory:     C:\projects\my-flask-app\.localagent.memory.json
  Index:      C:\projects\my-flask-app\.localagent.index.json
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type a question, a /command, or /exit to quit.

>
```

On **first launch**, the agent automatically:
1. Scans all project files
2. Builds an AST index (functions, classes, imports)
3. Creates `.localagent.index.json`, `.localagent.memory.json`, `.localagent.logs.txt`
4. Logs `"Project initialized"`

You are now ready to work.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                        YOU TYPE                             │
│                    "explain auth.py"                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │     ORCHESTRATOR       │  Classifies your task
              │  (needs retrieval?     │  (question / edit / plan)
              │   needs planner?)      │
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   RETRIEVAL ENGINE     │  AST index + FAISS search
              │  (finds relevant code) │  Budget: 2500 chars max
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │     WORKER LLM         │  Qwen 2.5 Coder 7B
              │  (generates answer     │  Streaming output
              │   or tool call)        │
              └───────────┬────────────┘
                          │
                    ┌─────┴──────┐
                    │            │
                    ▼            ▼
            ┌──────────┐  ┌───────────┐
            │ TOOL CALL │  │  RESPONSE │
            │ (execute  │  │  (stream  │
            │  & retry) │  │  to you)  │
            └─────┬─────┘  └─────┬─────┘
                  │              │
                  ▼              ▼
              ┌────────────────────────┐
              │       CRITIC LLM       │  Validates response
              │   (max 2 passes)       │  Checks for hallucination
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │    FINAL OUTPUT        │  Streamed to your terminal
              │   + saved to logs      │
              └────────────────────────┘
```

---

## All Commands

### File Operations

| Command | What it does | Example |
|---|---|---|
| `/read <file>` | Display file contents | `/read src/app.py` |
| `/write <file> <content>` | Create/overwrite a file | `/write test.txt hello world` |
| `/ls` | List all files in workspace | `/ls` |
| `/edit <file> <instruction>` | AI-powered edit with diff preview | `/edit utils.py add error handling` |

### Index & Search

| Command | What it does | Example |
|---|---|---|
| `/index` | Rebuild project index from scratch | `/index` |
| `/showindex` | Display raw index data | `/showindex` |
| `/find <keyword>` | Search for a symbol, file, or function | `/find authenticate` |

### Memory

| Command | What it does | Example |
|---|---|---|
| `/remember <key> <value>` | Store a fact about this project | `/remember db postgres` |
| `/forget <key>` | Delete a stored fact | `/forget db` |
| `/memory` | Show all stored facts | `/memory` |

### System

| Command | What it does |
|---|---|
| `/exit` | Quit the agent |

---

## Agent Mode

Type any natural language without a `/` prefix — the agent enters **autonomous mode**:

```
> what does run_worker do?

> explain the authentication flow in this project

> find all files that use the database connection

> why is this test failing?

> refactor the error handling in cli.py
```

### Streaming

Responses stream token-by-token in real-time. You see the answer building character by character — just like Claude Code. If the agent is making a tool call (JSON), it buffers silently until done, then executes.

### Clarification Mode

If the agent is uncertain, it **stops and asks you** instead of guessing:

```
I need clarification before continuing.
Reply with option or full path (or 'n' to stop):
```

Or after the Critic flags uncertainty:

```
Critic flagged response. I am not fully sure.
Proceed anyway? (y/n or clarification):
```

- `y` → accept the response
- `n` → abort
- Anything else → your text is injected as additional context and the agent retries

---

## Autonomous Tool Calls

The LLM can decide to use tools on its own. These are the available tools:

| Tool | What it does | Requires approval? |
|---|---|---|
| `read_file` | Read a file for context | No (safe) |
| `list_files` | List directory | No (safe) |
| `search_index` | Search code index | No (safe) |
| `replace_chunk` | Targeted find-and-replace edit | No (safe, precise) |
| `run_command` | Execute a shell command | **YES — asks y/n** |

### How `run_command` works:

```
> run the tests

Tool Call: run_command({'command': 'pytest tests/'})
Execute 'pytest tests/'? (y/n): y

Exit code 0
STDOUT:
4 passed in 1.2s
```

**Nothing executes until you type `y`.** Output is truncated to the last 1000 characters to protect the model's context window.

### Tool loop limits:

- Maximum **2 tool calls** per question
- Maximum **2 critic retry passes**
- If parsing fails, the raw text is shown as-is (never crashes)

---

## File Editing

### `/edit` Command (Interactive, with diff preview)

```
> /edit src/auth.py add input validation to the login function
```

What happens:
1. The agent reads the current file
2. The LLM generates the edited version
3. You see a **color-coded diff**:
   ```
   - old_line
   + new_line
   ```
4. You confirm: `Apply changes? (y/n)`
5. Only applied if you say `y`

### `replace_chunk` Tool (Autonomous, targeted)

When you ask the agent to fix something conversationally, it uses `replace_chunk` — a targeted string replacement. It only changes the exact lines that need changing, not the full file. This is critical for a 7B model that can't reliably regenerate 500-line files.

---

## Project Memory

Memory lets you teach the agent permanent facts about your project.

### Store facts:

```
> /remember framework flask
> /remember database postgresql
> /remember convention use-type-hints-always
> /remember deploy heroku
> /remember style black-formatter
```

### How memory works:

Every time the agent runs, **all memory entries are injected** into the LLM's system prompt:

```
PROJECT MEMORY:
{
  "framework": "flask",
  "database": "postgresql",
  "convention": "use-type-hints-always"
}
```

The model sees this on every single response. It never forgets.

### Limits:

- Maximum **50 entries** (oldest are auto-dropped)
- Memory is project-scoped (each project has its own)
- Memory persists across sessions

---

## Project Isolation

Each project directory is a **completely isolated workspace**:

```
C:\projects\flask-app\
├── .localagent.index.json      ← this project's code index
├── .localagent.memory.json     ← this project's memory
├── .localagent.logs.txt        ← this project's execution history
├── app.py
└── ...

C:\projects\react-app\
├── .localagent.index.json      ← completely separate
├── .localagent.memory.json     ← completely separate
├── .localagent.logs.txt        ← completely separate
├── src/
└── ...
```

- You can run **multiple agents simultaneously** on different projects
- Memory, index, and logs **never interfere** across projects
- The sandbox is **locked** to the project root — the agent cannot access files outside it

---

## Storage & Limits

Abyss Ossis is **garbage-proof by design**:

| Artifact | Strategy | Max Size |
|---|---|---|
| **Memory** | Capped at 50 entries, oldest auto-dropped | ~5 KB |
| **Index** | Always rebuilt from scratch via `/index`, never appended | Proportional to project |
| **Logs** | Rolling window — keeps last 500 lines only | ~50 KB |

Nothing grows unbounded. Nothing accumulates garbage.

---

## Architecture

```
local_agent/
├── cli.py                    # Main interactive loop, tool routing, streaming
├── config.py                 # Model name, temperature, context limits
├── requirements.txt          # Python dependencies
│
├── core/
│   ├── session.py            # ProjectSession — per-project isolation
│   ├── orchestrator.py       # Task classification (question/edit/plan)
│   ├── worker.py             # LLM prompt builder + Ollama execution
│   ├── critic.py             # Response validation (max 2 passes)
│   ├── planner.py            # Step-by-step plan generation
│   ├── sandbox.py            # Path security — locks to project root
│   ├── guards.py             # requires_more_info() checks
│   ├── tool_router.py        # Auto-detect /ls, /read from plain text
│   ├── tool_schema.py        # Tool registry (read_file, replace_chunk, etc.)
│   ├── logger.py             # Logging setup
│   └── editor.py             # Editor utilities
│
├── systems/
│   ├── ollama_client.py      # Ollama API wrapper + streaming
│   ├── memory.py             # Per-project JSON memory (load/save/remember/forget)
│   ├── state.py              # Conversation state (message history)
│   ├── semantic_index.py     # FAISS vector index for semantic search
│   └── rag.py                # RAG retrieval utilities
│
├── tools/
│   ├── code_indexer.py       # AST parser — extracts functions, classes, imports
│   ├── index_storage.py      # Index save/load/search (per-session)
│   ├── context_builder.py    # Builds context string from search results
│   ├── file_reader.py        # Safe file reading
│   ├── file_writer.py        # Safe file writing
│   ├── directory_reader.py   # List files in workspace
│   ├── diff_viewer.py        # Color-coded diff display
│   ├── edit_utils.py         # Edit prompt builder
│   ├── chunker.py            # Text chunking utilities
│   ├── embedder.py           # Text embedding for FAISS
│   ├── search_code.py        # Code search utilities
│   └── run_tests.py          # Test runner
│
├── data/                     # Legacy data directory
└── prompts/                  # Prompt templates
```

---

## Configuration

Edit `config.py` to customize:

```python
MODEL = "qwen2.5-coder:7b"   # Change model (e.g., "codellama:13b")
TEMPERATURE = 0.2             # Lower = more deterministic
MAX_CONTEXT = 4096            # Context window budget
WHITELIST_DIRS = []            # Allow access outside workspace
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| `Cannot connect to Ollama` | Ollama not running | Run `ollama serve` in a separate terminal |
| `Usage: python cli.py run <project_path>` | Missing arguments | Use `python cli.py run C:\path\to\project` |
| Agent gives generic/wrong answers | Index is outdated | Run `/index` to rebuild |
| Agent hallucinates code | No context found | Use `/find` to check what's indexed, then `/index` |
| Agent is slow | CPU inference | Normal for 7B on CPU. GPU accelerates 5-10x |
| `Access denied: Path outside workspace` | Sandbox blocked it | The file is outside your project root |
| Tool call fails to parse | Model output bad JSON | Agent auto-falls back to plain text. Retry. |
| Memory full | 50+ entries | Oldest are auto-dropped. Use `/forget` to clean up. |

---

## Tips for Best Results

1. **Always `/index` after major file changes** — the agent relies on the index to find relevant code
2. **Use `/remember` for architecture decisions** — the model reads these on every response
3. **Be specific** — `"explain the login function in auth.py"` works far better than `"how does this work"`
4. **Use `/find` before asking** — check what the index knows, so you can ask targeted questions
5. **Don't paste huge code blocks** — let the retrieval system find code for you
6. **Re-index when switching branches** — `/index` rebuilds from scratch
7. **Use `/edit` for small changes** — the diff preview lets you verify before applying
8. **Trust the clarification prompts** — if the agent pauses to ask, give it specific info

---

## Comparison with Claude Code

| Feature | Claude Code | Abyss Ossis |
|---|---|---|
| Model | Claude 3.5 Sonnet (200B+) | Qwen 2.5 Coder 7B |
| Cost | $20/month | **Free** |
| Privacy | Cloud | **100% Local** |
| Internet required | Yes | **No** |
| Context window | 200K tokens | ~8K tokens (managed by budget) |
| File editing | Full rewrite | **Targeted patch edits** |
| Tool execution | Auto | **User-approved (y/n)** |
| Project memory | Implicit | **Explicit `/remember` system** |
| Streaming | Yes | **Yes** |
| Multi-project | Yes | **Yes (isolated sessions)** |
| Code indexing | Built-in | **AST + FAISS semantic** |

---

*Built with ❤️ for developers who want AI coding without the cloud.*
## Star History

If this project helps you, consider starring it ⭐
