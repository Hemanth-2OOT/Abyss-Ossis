class AgentState:
    def __init__(self):
        self.messages = []
        self.plan = []
        self.memory = []

    def add_message(self, role, content, **kwargs):
        msg = {
            "role": role,
            "content": content
        }
        msg.update(kwargs)
        self.messages.append(msg)