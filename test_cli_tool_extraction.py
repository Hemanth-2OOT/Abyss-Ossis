import unittest

from cli import _extract_embedded_tool_call

class TestToolExtraction(unittest.TestCase):
    def test_extract_exact_json(self):
        text = '{"type":"tool_call","tool":"read_file","args":{"path":"app.py"}}'
        result = _extract_embedded_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("tool"), "read_file")

    def test_extract_with_markdown_fences(self):
        text = '```json\n{"type":"tool_call","tool":"read_file","args":{"path":"app.py"}}\n```'
        result = _extract_embedded_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("tool"), "read_file")

    def test_extract_with_plain_text_preamble(self):
        text = 'I need to read the file first.\n{"type":"tool_call","tool":"read_file","args":{"path":"app.py"}}'
        result = _extract_embedded_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("tool"), "read_file")

    def test_extract_with_preamble_and_fences(self):
        text = 'Here is the tool call:\n```json\n{"type":"tool_call","tool":"read_file","args":{"path":"app.py"}}\n```'
        result = _extract_embedded_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("tool"), "read_file")

    def test_extract_consecutive_json_objects(self):
        text = '{"reasoning": "checking files"}\n{"type":"tool_call","tool":"list_files","args":{}}'
        result = _extract_embedded_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("tool"), "list_files")

if __name__ == "__main__":
    unittest.main()
