# File Operations Skill

## When to Activate
Activate when the request involves reading, listing, searching, or navigating files and directories in the project workspace.

**Trigger keywords:** read file, list files, search, open file, directory, find, show file, what files, contents of, file contents

---

## Best Practices

- Always read a file before proposing edits to it. Never guess at its contents.
- Use `list_files` to discover what exists before assuming filenames.
- After a successful `read_file`, use the returned content directly — do not call `read_file` again for the same file.
- For file modifications: read → plan changes → write. Never write blind.
- Prefer relative paths. Do not prepend absolute system paths.
- When a path is not found, list the parent directory to confirm the structure before retrying.

---

## Common Mistakes

- Calling `read_file` twice on the same file without a good reason.
- Writing to a file without having read it first (risks overwriting existing content).
- Assuming a file exists without listing the directory.
- Using an alias tool name (`file_read`, `cat`, `ls`) instead of canonical names (`read_file`, `list_files`).
- Guessing file contents when `read_file` is available.

---

## Canonical Tool Names

| Alias | Canonical name |
|---|---|
| `file_read`, `read`, `cat`, `open_file` | `read_file` |
| `file_list`, `ls` | `list_files` |
| `grep` | `search_files` |

Always use the canonical name in tool calls.

---

## Checklist

- [ ] Listed directory before assuming file paths
- [ ] Read the file before proposing modifications
- [ ] Used canonical tool names (`read_file`, `list_files`)
- [ ] Did not call `read_file` twice for the same file
- [ ] Used relative paths, not absolute system paths

---

## Few-Shot Examples

### Example 1: Inspect then edit
```json
{"type": "tool_call", "tool": "read_file", "args": {"path": "templates/index.html"}}
```
*Receive file content → plan edit → write back with changes.*

### Example 2: Discover structure first
```json
{"type": "tool_call", "tool": "list_files", "args": {}}
```
*Use the returned listing to confirm the exact filename before reading.*

### Example 3: Search for a symbol
```json
{"type": "tool_call", "tool": "search_files", "args": {"query": "def process_order"}}
```
*Use search results to identify the correct file before reading it.*
