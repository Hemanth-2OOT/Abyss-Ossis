# Debugging Skill

## When to Activate
Activate when the request involves finding and fixing bugs, interpreting error messages, tracebacks, unexpected behaviour, failing tests, or crashes.

**Trigger keywords:** bug, fix, error, traceback, failing, crash, broken, exception, AttributeError, TypeError, KeyError, ImportError, undefined, not working

---

## Best Practices

- Read the traceback from bottom to top. The last frame is closest to the root cause.
- Reproduce the bug in the smallest possible code snippet before fixing.
- Check the type of variables at the crash site — many bugs are type mismatches.
- Add a `print()` or `logging.debug()` before and after the suspected line to confirm execution flow.
- Verify assumptions: don't assume a variable has a value — log it.
- Fix the root cause, not the symptom. Wrapping errors in `try/except` without handling is a symptom fix.
- After fixing, ask: "What other code paths could trigger the same bug?"

---

## Common Mistakes

- Assuming the error message is always the exact problem — sometimes the error is one call upstream.
- Fixing the wrong line after misreading a long traceback.
- Catching an exception silently without logging it.
- Not checking whether the bug is deterministic or race-condition related.
- Over-engineering the fix — prefer a targeted minimal change.

---

## Checklist

- [ ] Read the full traceback, not just the last line
- [ ] Identified the root cause (not just the symptom)
- [ ] Fix is targeted — changes only what's needed
- [ ] No silent `except:` clauses added as workaround
- [ ] Checked whether the same bug can occur in related code paths
- [ ] Verified fix with the same input that triggered the bug

---

## Few-Shot Examples

### Example 1: Traceback analysis
```
AttributeError: 'NoneType' object has no attribute 'strip'
  File "app.py", line 42, in process
    name = user.get("name").strip()
```
**Fix:** `user.get("name")` returned `None`. Guard with `or ""`:
```python
name = (user.get("name") or "").strip()
```

### Example 2: KeyError in dict access
```
KeyError: 'token'
  File "auth.py", line 18, in validate
    return data["token"]
```
**Fix:** Use `.get()` with a default or check first:
```python
token = data.get("token")
if not token:
    raise ValueError("Missing token in response")
```

### Example 3: Root cause vs symptom
```python
# Symptom fix (wrong)
try:
    result = compute(x)
except Exception:
    result = None

# Root cause fix (right) — find why compute(x) fails
def compute(x):
    if x is None:
        raise ValueError("x must not be None")
    return x * 2
```
