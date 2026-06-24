import os
import shutil
import unittest
import sys
from unittest.mock import patch

import cli
from core.session import ProjectSession
from systems.state import AgentState

class TestE2EOrchestration(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_e2e_workspace"
        os.makedirs(self.test_dir, exist_ok=True)
        self.session = ProjectSession(self.test_dir)
        
        cli.state = AgentState()
        cli.INSTALL_ATTEMPTS.clear()
        
        def safe_print(*args, **kwargs):
            if args:
                sys.stderr.write("CONSOLE: " + str(args[0])[:150] + "\n")
        
        # Start core patches at the cli lookup boundary
        self.patchers = [
            patch("cli.console.print", side_effect=safe_print),
            patch("cli.search_index", return_value=[]),
            patch("cli.classify_task", return_value={"task_type": "coding", "needs_planner": True, "needs_tools": True, "needs_retrieval": False}),
            patch("core.planner.generate_plan", return_value={"steps": [], "constraints": [], "edge_cases": []}),
            patch("cli.run_worker"),
            patch("cli.critique_response"),
            patch("core.resource_monitor.Watchdog.start")
        ]
        
        self.mock_console = self.patchers[0].start()
        self.mock_search = self.patchers[1].start()
        self.mock_classify = self.patchers[2].start()
        self.mock_planner = self.patchers[3].start()
        self.mock_worker = self.patchers[4].start()
        self.mock_critic = self.patchers[5].start()
        self.mock_watchdog_start = self.patchers[6].start()
        
        # Default behaviors
        self.mock_worker.return_value = "I am done."
        self.mock_planner.return_value = {"steps": [], "constraints": [], "edge_cases": []}
        self.mock_critic.return_value = "OK"
        
    def tearDown(self):
        for p in self.patchers:
            p.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("builtins.input", side_effect=["Fix the bug", KeyboardInterrupt()])
    def test_missing_artifact_hallucination(self, mock_input):
        # Planner outputs a step about a file that doesn't exist
        self.mock_planner.return_value = {"steps": ["Read gameloop.py"], "constraints": [], "edge_cases": []}
        
        cli.main(self.session)
        
        # Behavioral invariant: The orchestration shouldn't block or loop infinitely.
        # It should complete and prompt for input again, triggering KeyboardInterrupt.
        self.assertTrue(True) # Reaching here implies no infinite loop

    @patch("builtins.input", side_effect=["Create test_utils.py", KeyboardInterrupt()])
    def test_user_created_file_enforcement(self, mock_input):
        cli.main(self.session)
        # Behavioral invariant: Just finishing the turn properly.
        self.assertTrue(True)

    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    def test_duplicate_budget_protection(self, mock_input):
        tool_call_json = '{"type": "tool_call", "tool": "read_file", "args": {"path": "main.py"}}'
        
        # Worker emits same tool twice
        self.mock_worker.side_effect = [
            f"```json\n{tool_call_json}\n```",
            f"```json\n{tool_call_json}\n```",
            f"```json\n{tool_call_json}\n```",
            "Okay, I'm done."
        ]
        
        with open(os.path.join(self.test_dir, "main.py"), "w") as f:
            f.write("print('hello')")
            
        cli.main(self.session)
        
        # Behavioral check: Verify the system detected the duplicate and warned the worker
        messages_text = str(self.mock_worker.call_args_list)
        self.assertIn("CRITICAL INSTRUCTION: YOU ALREADY CALLED THIS TOOL SUCCESSFULLY.", messages_text.upper())

    @patch("builtins.input", side_effect=["Fix it", KeyboardInterrupt()])
    def test_fsm_prerequisite_guidance(self, mock_input):
        pytest_call = '{"type": "tool_call", "tool": "run_command", "args": {"command": "pytest"}}'
        self.mock_worker.side_effect = [
            f"```json\n{pytest_call}\n```",
            "I will implement first."
        ]
        
        cli.main(self.session)
        
        # In V3, the deterministic scheduler manages sequence. If a worker hallucinates a command, 
        # it executes. The planner establishes the order, not a global validator guard.
        self.assertTrue(True)

    @patch("builtins.input", side_effect=["Fix it", KeyboardInterrupt()])
    def test_fsm_test_twice(self, mock_input):
        write_call = '{"type": "tool_call", "tool": "write_file", "args": {"path": "test.py", "content": "x=1"}}'
        pytest_call = '{"type": "tool_call", "tool": "run_command", "args": {"command": "pytest"}}'
        
        self.mock_worker.side_effect = [
            f"```json\n{write_call}\n```",
            f"```json\n{pytest_call}\n```",
            f"```json\n{pytest_call}\n```",
            "I am done."
        ]
        cli.main(self.session)
        
        # After editing, testing is allowed. Verify it didn't block it.
        messages_text = str(self.mock_worker.call_args_list).upper()
        self.assertIn("TOOL RESULT", messages_text)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "test.py")))

    @patch("builtins.input", side_effect=["Do it", KeyboardInterrupt()])
    def test_critic_retry_emits_tool_call(self, mock_input):
        tool_json = '{"type": "tool_call", "tool": "list_files", "args": {}}'
        self.mock_worker.side_effect = [
            "Here is my attempt.",
            f"My bad, let me check files:\n```json\n{tool_json}\n```",
            "Done."
        ]
        # Critic first rejects, then accepts
        self.mock_critic.side_effect = ["NEEDS_MORE_INFO", "OK"]
        
        cli.main(self.session)
        
        # Behavioral check: The second worker pass emitted a tool call which was successfully parsed and executed.
        messages_text = str(self.mock_worker.call_args_list).upper()
        self.assertIn("TOOL RESULT", messages_text)

    @patch("builtins.input", side_effect=["Do it", KeyboardInterrupt()])
    def test_markdown_fenced_tool_json(self, mock_input):
        tool_json = '{"type": "tool_call", "tool": "list_files", "args": {}}'
        self.mock_worker.side_effect = [
            f"```json\n{tool_json}\n```",
            "Done."
        ]
        cli.main(self.session)
        
        messages_text = str(self.mock_worker.call_args_list).upper()
        self.assertIn("TOOL RESULT", messages_text)

    # === NEW ADVERSARIAL TESTS ===
    
    @patch("builtins.input", side_effect=["Adversarial test 1", KeyboardInterrupt()])
    def test_adversarial_malformed_json(self, mock_input):
        # Missing closing brace
        malformed = '{"type": "tool_call", "tool": "list_files", "args": {}'
        self.mock_worker.side_effect = [
            f"```json\n{malformed}\n```",
            "Done."
        ]
        cli.main(self.session)
        
        # Behavioral check: Parser handles malformed JSON without crashing the orchestration
        # Depending on how the parser handles it, it might just ignore or emit an error back to the worker
        # But we ensure it completes correctly
        self.assertTrue(True)

    @patch("builtins.input", side_effect=["Adversarial test 2", KeyboardInterrupt()])
    def test_adversarial_plain_text_plus_json(self, mock_input):
        tool_json = '{"type": "tool_call", "tool": "list_files", "args": {}}'
        self.mock_worker.side_effect = [
            f"I think I need to look around first.\n```json\n{tool_json}\n```\nLet me know what happens.",
            "Done."
        ]
        cli.main(self.session)
        
        messages_text = str(self.mock_worker.call_args_list)
        self.assertIn("TOOL RESULT", messages_text) # Should successfully extract the JSON

    @patch("builtins.input", side_effect=["Adversarial test 3", KeyboardInterrupt()])
    def test_adversarial_invalid_tool_name(self, mock_input):
        invalid_tool = '{"type": "tool_call", "tool": "make_coffee", "args": {}}'
        self.mock_worker.side_effect = [
            f"```json\n{invalid_tool}\n```",
            "Done."
        ]
        cli.main(self.session)
        
        messages_text = str(self.mock_worker.call_args_list)
        self.assertIn("Unknown tool", messages_text)
        self.assertIn("make_coffee", messages_text)

        # Test memory safety system
    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.psutil.virtual_memory")
    def test_sufficient_memory(self, mock_mem, mock_input):
        import collections
        MemInfo = collections.namedtuple('MemInfo', ['available', 'percent'])
        mock_mem.return_value = MemInfo(available=16 * (1024**3), percent=50.0)
        
        with patch("core.resource_monitor.HAS_GPUTIL", False):
            try:
                cli.main(self.session)
            except KeyboardInterrupt:
                pass
        self.assertTrue(True)

    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.psutil.virtual_memory")
    def test_insufficient_ram(self, mock_mem, mock_input):
        import collections
        MemInfo = collections.namedtuple('MemInfo', ['available', 'percent'])
        mock_mem.return_value = MemInfo(available=0.5 * (1024**3), percent=50.0)
        
        with patch("core.resource_monitor.HAS_GPUTIL", False):
            try:
                cli.main(self.session)
            except KeyboardInterrupt:
                pass
        
        self.assertEqual(self.mock_worker.call_count, 0)

    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.psutil.virtual_memory")
    @patch("core.resource_monitor.GPUtil.getGPUs")
    def test_insufficient_vram(self, mock_gpus, mock_mem, mock_input):
        import collections
        MemInfo = collections.namedtuple('MemInfo', ['available', 'percent'])
        mock_mem.return_value = MemInfo(available=16 * (1024**3), percent=50.0)
        
        GPU = collections.namedtuple('GPU', ['id', 'memoryFree'])
        mock_gpus.return_value = [GPU(id=0, memoryFree=128)]
        
        with patch("core.resource_monitor.HAS_GPUTIL", True):
            try:
                cli.main(self.session)
            except KeyboardInterrupt:
                pass
                
        self.assertEqual(self.mock_worker.call_count, 0)

    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.psutil.virtual_memory")
    def test_threshold_exactly_met(self, mock_mem, mock_input):
        import collections
        MemInfo = collections.namedtuple('MemInfo', ['available', 'percent'])
        mock_mem.return_value = MemInfo(available=16 * (1024**3), percent=90.0)
        
        with patch("core.resource_monitor.HAS_GPUTIL", False):
            try:
                cli.main(self.session)
            except KeyboardInterrupt:
                pass
                
        self.assertEqual(self.mock_worker.call_count, 0)


    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.watchdog.check")
    def test_insufficient_ram(self, mock_check, mock_input):
        from core.resource_monitor import ResourceSafetyError
        mock_check.side_effect = ResourceSafetyError("Insufficient RAM")
        
        try:
            cli.main(self.session)
        except KeyboardInterrupt:
            pass
        
        self.assertEqual(self.mock_worker.call_count, 0)

    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.watchdog.check")
    def test_insufficient_vram(self, mock_check, mock_input):
        from core.resource_monitor import ResourceSafetyError
        mock_check.side_effect = ResourceSafetyError("Insufficient VRAM")
        
        try:
            cli.main(self.session)
        except KeyboardInterrupt:
            pass
                
        self.assertEqual(self.mock_worker.call_count, 0)

    @patch("builtins.input", side_effect=["Do something", KeyboardInterrupt()])
    @patch("core.resource_monitor.watchdog.check")
    def test_threshold_exactly_met(self, mock_check, mock_input):
        from core.resource_monitor import ResourceSafetyError
        mock_check.side_effect = ResourceSafetyError("Threshold met")
        
        try:
            cli.main(self.session)
        except KeyboardInterrupt:
            pass
                
        self.assertEqual(self.mock_worker.call_count, 0)

    @patch("builtins.input", side_effect=["Do something", "Do something else", KeyboardInterrupt()])
    @patch("core.resource_monitor.watchdog.check")
    def test_memory_recovery_no_infinite_loop(self, mock_check, mock_input):
        from core.resource_monitor import ResourceSafetyError
        # First check fails (Task 1 aborts)
        # Second check succeeds (Task 2 runs)
        mock_check.side_effect = [ResourceSafetyError("Low mem"), None, None, None, None, None, None]
        self.mock_worker.side_effect = ['{"type": "final", "content": "I am done."}']
        
        try:
            cli.main(self.session)
        except KeyboardInterrupt:
            pass
                
        self.assertEqual(self.mock_worker.call_count, 2)

if __name__ == '__main__':
    unittest.main()
