def requires_more_info(task, user_input):
    task_type = task["task_type"]
    text = user_input.lower()

    if task_type == "debugging":
        keywords = [
            "traceback",
            "error log",
            "stack trace",
            "code",
            "exception"
        ]

        if not any(word in text for word in keywords):
            return True

    return False