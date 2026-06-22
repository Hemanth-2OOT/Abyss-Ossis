# Refactoring Skill

## When to Activate
Activate when the request involves improving existing code without changing its behaviour: reducing duplication, clarifying names, splitting large functions, extracting helpers, or simplifying logic.

**Trigger keywords:** refactor, clean, optimize, improve, simplify, restructure, reorganize, reduce duplication, extract, rename

---

## Best Practices

- Refactor in small, safe steps. Verify after each step.
- Rename first — a good name often reveals the right structure.
- Extract a function when you see the same logic twice or more.
- Replace magic numbers and strings with named constants.
- Reduce nesting depth. Prefer early returns over deeply nested `if` blocks.
- Break large classes into smaller, single-responsibility classes.
- Prefer pure functions — functions with no side effects are easiest to refactor.
- Keep refactors separate from feature changes. Don't mix in new behaviour.

---

## Common Mistakes

- Changing behaviour while "refactoring" — this introduces regressions.
- Renaming inconsistently (e.g., renaming in the definition but not at all call sites).
- Making things more abstract than needed (over-engineering).
- Removing code that looks unused without checking all callers.
- Forgetting to update comments and docstrings after renaming.

---

## Checklist

- [ ] No behaviour was changed, only structure
- [ ] All renamed symbols updated at every call site
- [ ] No magic numbers remain (use named constants)
- [ ] Functions ≤ 30 lines after refactor
- [ ] Docstrings and comments updated
- [ ] No dead code left behind

---

## Few-Shot Examples

### Example 1: Early return to reduce nesting
```python
# Before
def get_discount(user):
    if user:
        if user.is_premium:
            if user.years > 2:
                return 0.3
    return 0.0

# After
def get_discount(user):
    if not user or not user.is_premium:
        return 0.0
    if user.years > 2:
        return 0.3
    return 0.0
```

### Example 2: Extract repeated logic
```python
# Before
tax_a = price_a * 0.18
tax_b = price_b * 0.18

# After
TAX_RATE = 0.18

def compute_tax(price):
    return price * TAX_RATE

tax_a = compute_tax(price_a)
tax_b = compute_tax(price_b)
```

### Example 3: Replace magic string
```python
# Before
if status == "active":
    ...

# After
ACTIVE_STATUS = "active"

if status == ACTIVE_STATUS:
    ...
```
