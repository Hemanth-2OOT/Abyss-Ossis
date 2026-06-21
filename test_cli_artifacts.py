import os
import shutil
import unittest
from cli import _infer_expected_artifacts

class DummySession:
    def __init__(self, root):
        self.root = root

class TestInferExpectedArtifacts(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_artifacts_dir"
        os.makedirs(self.test_dir, exist_ok=True)
        self.session = DummySession(self.test_dir)
        
        # Create some real files
        with open(os.path.join(self.test_dir, "main.py"), "w") as f:
            f.write("print('hello')")
            
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_planner_hallucination_ignored(self):
        # Planner hallucinates gameloop.py, which does NOT exist.
        user_input = "Fix the game logic."
        plan_steps = ["1. Read gameloop.py", "2. Edit main.py"]
        
        artifacts = _infer_expected_artifacts(user_input, plan_steps, self.session)
        
        # gameloop.py should be ignored because it doesn't exist and wasn't requested.
        self.assertNotIn("gameloop.py", artifacts)
        # main.py should be included because it DOES exist.
        self.assertIn("main.py", artifacts)

    def test_user_requested_new_file_enforced(self):
        # User explicitly requests to create test_utils.py, which DOES NOT exist initially.
        user_input = "Create test_utils.py"
        plan_steps = ["1. Write test_utils.py"]
        
        artifacts = _infer_expected_artifacts(user_input, plan_steps, self.session)
        
        # test_utils.py MUST be included because the user explicitly asked for it.
        self.assertIn("test_utils.py", artifacts)

if __name__ == "__main__":
    unittest.main()
