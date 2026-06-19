class AgentState:
    def __init__(self):
        self.messages = []
        self.current_task = None
        self.plan = []
        self.memory = []
        self.retrieved_docs = []
        self.tool_outputs = []

    def add_message(self, role, content):
        self.messages.append({
            "role": role,
            "content": content
        })