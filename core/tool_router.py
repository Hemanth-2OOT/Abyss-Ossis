def detect_tool(user_input):
    text = user_input.lower()

    if "show files" in text or "list files" in text:
        return {"tool": "ls"}

    if ".py" in text and ("read" in text or "check" in text or "open" in text):
        words = user_input.split()

        for word in words:
            if word.endswith(".py"):
                return {
                    "tool": "read",
                    "path": word
                }

    return None