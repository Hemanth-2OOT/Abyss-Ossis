# Reasoning Skill

## When to Activate
Activate when the request asks for explanation, understanding, analysis, or a reasoned answer rather than direct code production.

**Trigger keywords:** explain, why, how does, reason, understand, what is, describe, what happens, walk me through, tell me, summarise

---

## Best Practices

- Identify what the user actually wants to understand before answering.
- Use concrete examples to illustrate abstract concepts.
- Break explanations into numbered steps when describing a process.
- State assumptions explicitly before reasoning from them.
- If the answer depends on context, say so — don't pretend certainty.
- Prefer short precise sentences over long winding paragraphs.
- Distinguish between "what it does" and "why it was designed that way".
- Do not pad the answer with filler phrases ("great question", "certainly").

---

## Common Mistakes

- Answering a slightly different question than was asked.
- Explaining too much at once — overwhelming instead of clarifying.
- Using jargon without defining it first.
- Hedging with vague qualifiers ("usually", "typically", "might") when a precise answer exists.
- Forgetting to ground the explanation in the user's specific code or project.

---

## Checklist

- [ ] Understood what specifically the user wants explained
- [ ] Used at least one concrete example
- [ ] No unexplained jargon
- [ ] Cited specific file or symbol names from the project where relevant
- [ ] Answer is focused (not a general tutorial)

---

## Few-Shot Examples

### Example 1: Explain a concept with an example
**Q:** Why does Python have GIL?
**A:** The Global Interpreter Lock (GIL) is a mutex that prevents multiple native threads from executing Python bytecode simultaneously. It exists because CPython's memory management (reference counting) is not thread-safe without it. For CPU-bound tasks this limits parallelism; for I/O-bound tasks threads still help because the GIL is released during blocking I/O calls.

### Example 2: Walk through code behaviour
**Q:** Why does `list.sort()` return None?
**A:** `list.sort()` sorts in place and returns `None` by design — Python signals that the operation mutated the object rather than producing a new one. If you need a sorted copy, use `sorted(lst)` which returns a new list.

### Example 3: Project-specific reasoning
**Q:** Why is cli.py importing AgentState from systems.state?
**A:** `AgentState` tracks the conversation message buffer across turns. `cli.py` owns the main loop and needs to append each user message and assistant response so the full history is sent to the worker LLM on the next call.
