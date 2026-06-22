# Python Skill

## When to Activate
Activate when the request involves Python code: functions, classes, modules, scripts, imports, type hints, async code, data structures, or standard library usage.

**Trigger keywords:** python, def, class, import, script, module, async, await, list, dict, dataclass

---

## Best Practices

- Prefer explicit over implicit. Name variables and functions clearly.
- Use type hints for function signatures.
- Favour `pathlib.Path` over `os.path` for filesystem work.
- Use f-strings for string formatting.
- Prefer `with` blocks for file and resource handling.
- Keep functions short (≤ 30 lines). Extract helpers if needed.
- Avoid mutable default arguments (`def f(x=[])`).
- Use dataclasses or named tuples for structured data instead of raw dicts.
- Raise specific exceptions, not bare `Exception`.
- Use `__all__` in modules to declare public API.

---

## Common Mistakes

- Mutating a list while iterating over it.
- Using `is` instead of `==` for value comparison.
- Shadowing built-ins (`list`, `id`, `type`, `input`).
- Forgetting `self` in class methods.
- Missing `return` in functions that should return a value.
- Using `except:` (bare) instead of `except Exception as e:`.
- Forgetting to close files without a context manager.
- Circular imports between modules.

---

## Checklist

- [ ] All functions have type hints on parameters and return type
- [ ] No mutable default arguments
- [ ] Resources opened with `with` blocks
- [ ] Specific exceptions caught and logged
- [ ] No shadowed built-ins
- [ ] Function is ≤ 30 lines or extracted into helpers

---

## Few-Shot Examples

### Example 1: Reading a file safely
```python
# Bad
data = open("config.json").read()

# Good
from pathlib import Path
data = Path("config.json").read_text(encoding="utf-8")
```

### Example 2: Avoid mutable defaults
```python
# Bad
def append_item(item, lst=[]):
    lst.append(item)
    return lst

# Good
def append_item(item, lst=None):
    if lst is None:
        lst = []
    lst.append(item)
    return lst
```

### Example 3: Structured data
```python
# Bad
user = {"name": "Alice", "age": 30}

# Good
from dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int

user = User(name="Alice", age=30)
```
