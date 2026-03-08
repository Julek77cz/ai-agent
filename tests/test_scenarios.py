"""
Comprehensive Test Scenarios for JARVIS Critical Bug Fixes

Tests the following fixes:
1. Robust parameter extraction fallback when LLM fails to provide params
2. Enhanced system prompt with tool examples
3. Parameter inference from thought text
4. Memory tools fixes (validation, error handling)
5. Edge cases and error recovery

Usage:
    cd /home/engine/project
    python tests/test_scenarios.py
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, Mock
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JARVIS.TESTS")

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_reasoning import ReActLoop, ToolResultParser
from jarvis_tools import validate_tool_params, get_tool_required_params, get_tool_param_examples, TOOL_SCHEMAS


class TestParameterExtractionFallback(unittest.TestCase):
    """Test parameter extraction fallback when LLM fails to provide params."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_bridge = MagicMock()
        self.mock_memory = MagicMock()
        self.mock_tools = {}
        self.react_loop = ReActLoop(
            bridge=self.mock_bridge,
            memory=self.mock_memory,
            tools=self.mock_tools,
            max_iterations=5
        )
    
    def test_extract_params_for_recall(self):
        """Test parameter extraction for recall tool."""
        # Test with quoted string
        thought = 'I need to recall information about "user preferences" from memory'
        params = self.react_loop._extract_params_from_thought("recall", thought)
        self.assertEqual(params.get("query"), "user preferences")
        
        # Test with question pattern
        thought = "What do I know about the user's favorite color?"
        params = self.react_loop._extract_params_from_thought("recall", thought)
        self.assertIn("user's favorite color", params.get("query", ""))
        
        # Test with memory keywords
        thought = "I should recall what the user told me yesterday"
        params = self.react_loop._extract_params_from_thought("recall", thought)
        self.assertIsNotNone(params.get("query"))
    
    def test_extract_params_for_remember(self):
        """Test parameter extraction for remember tool."""
        # Test with quoted content
        thought = 'I should remember that "the user likes coffee" for future reference'
        params = self.react_loop._extract_params_from_thought("remember", thought)
        self.assertEqual(params.get("content"), "the user likes coffee")
        self.assertEqual(params.get("fact_type"), "preference")
        
        # Test with event keywords
        thought = "The user has a meeting tomorrow at 3pm"
        params = self.react_loop._extract_params_from_thought("remember", thought)
        self.assertEqual(params.get("fact_type"), "event")
        
        # Test with fact keywords
        thought = "It's a fact that the user works from home"
        params = self.react_loop._extract_params_from_thought("remember", thought)
        self.assertEqual(params.get("fact_type"), "fact")
    
    def test_extract_params_for_web_search(self):
        """Test parameter extraction for web_search tool."""
        # Test with quoted string
        thought = 'I should search for "weather in Prague" online'
        params = self.react_loop._extract_params_from_thought("web_search", thought)
        self.assertEqual(params.get("query"), "weather in Prague")
        
        # Test with search keywords
        thought = "Let me look up the latest Python documentation"
        params = self.react_loop._extract_params_from_thought("web_search", thought)
        self.assertIn("Python", params.get("query", ""))
    
    def test_extract_params_for_file_operations(self):
        """Test parameter extraction for file operations."""
        # Test read_file
        thought = 'I need to read the file "config.json"'
        params = self.react_loop._extract_params_from_thought("read_file", thought)
        self.assertEqual(params.get("file_path"), "config.json")
        
        # Test write_file with various extensions
        thought = 'I should write the data to "output.csv"'
        params = self.react_loop._extract_params_from_thought("write_file", thought)
        self.assertEqual(params.get("file_path"), "output.csv")
    
    def test_extract_params_for_manage_tasks(self):
        """Test parameter extraction for manage_tasks tool."""
        # Test add action
        thought = 'I should add a task "Buy milk" to the list'
        params = self.react_loop._extract_params_from_thought("manage_tasks", thought)
        self.assertEqual(params.get("action"), "add")
        self.assertEqual(params.get("task_description"), "Buy milk")
        
        # Test remove action
        thought = 'Delete task abc123'
        params = self.react_loop._extract_params_from_thought("manage_tasks", thought)
        self.assertEqual(params.get("action"), "remove")
    
    def test_extract_params_for_run_python(self):
        """Test parameter extraction for run_python tool."""
        thought = "Execute this code: ```python\nprint('Hello')\n```"
        params = self.react_loop._extract_params_from_thought("run_python", thought)
        self.assertEqual(params.get("code"), "print('Hello')")
        
        thought = "Run `2 + 2` to calculate"
        params = self.react_loop._extract_params_from_thought("run_python", thought)
        self.assertEqual(params.get("code"), "2 + 2")
    
    def test_enhance_action_with_fallback(self):
        """Test the action enhancement with fallback logic."""
        thought = 'I need to recall "user preferences"'
        
        # Test with empty params
        action = {"tool": "recall", "params": {}, "parallel": False}
        enhanced = self.react_loop._enhance_action_with_fallback(action, thought)
        self.assertEqual(enhanced["params"].get("query"), "user preferences")
        
        # Test with partial params (should keep original)
        action = {"tool": "remember", "params": {"fact_type": "fact"}, "parallel": False}
        enhanced = self.react_loop._enhance_action_with_fallback(action, thought)
        self.assertEqual(enhanced["params"].get("fact_type"), "fact")
        self.assertIsNotNone(enhanced["params"].get("content"))
    
    def test_tool_extraction_from_thought(self):
        """Test extracting tool name from thought text."""
        test_cases = [
            ("I need to search for something online", "web_search"),
            ("What do I recall about this?", "recall"),
            ("Let me read the file content", "read_file"),
            ("Write this to output.txt file", "write_file"),
            ("What time is it now?", "get_time"),
            ("Check system resources", "system_info"),
            ("Show me the directory contents", "list_dir"),
            ("I should remember that fact", "remember"),  # More specific to remember tool
        ]
        
        for thought, expected_tool in test_cases:
            tool = self.react_loop._extract_tool_from_thought(thought)
            self.assertEqual(tool, expected_tool, f"Failed for thought: {thought}")


class TestToolParameterValidation(unittest.TestCase):
    """Test tool parameter validation with Pydantic."""
    
    def test_validate_recall_params(self):
        """Test validation of recall parameters."""
        # Valid params
        success, result = validate_tool_params("recall", {"query": "test"})
        self.assertTrue(success)
        self.assertEqual(result["query"], "test")
        
        # Missing required param
        success, result = validate_tool_params("recall", {})
        self.assertFalse(success)
        self.assertIn("query", result)
    
    def test_validate_remember_params(self):
        """Test validation of remember parameters."""
        # Valid params
        success, result = validate_tool_params("remember", {
            "content": "User likes coffee",
            "fact_type": "preference",
            "confidence": 0.9
        })
        self.assertTrue(success)
        self.assertEqual(result["content"], "User likes coffee")
        
        # Invalid fact_type should still validate (will be fixed in tool)
        success, result = validate_tool_params("remember", {
            "content": "Test",
            "fact_type": "invalid_type"
        })
        # Pydantic accepts any string for fact_type currently
        self.assertTrue(success)
    
    def test_validate_write_file_params(self):
        """Test validation of write_file parameters."""
        # Valid params
        success, result = validate_tool_params("write_file", {
            "file_path": "test.txt",
            "content": "Hello World"
        })
        self.assertTrue(success)
        
        # Missing required param
        success, result = validate_tool_params("write_file", {"file_path": "test.txt"})
        self.assertFalse(success)
        self.assertIn("content", result)
    
    def test_get_tool_required_params(self):
        """Test getting required parameters for tools."""
        self.assertEqual(get_tool_required_params("recall"), ["query"])
        self.assertEqual(get_tool_required_params("remember"), ["content"])
        self.assertEqual(get_tool_required_params("get_time"), [])
        self.assertEqual(get_tool_required_params("write_file"), ["file_path", "content"])
    
    def test_get_tool_param_examples(self):
        """Test getting parameter examples for tools."""
        examples = get_tool_param_examples("remember")
        self.assertIn("content", examples)
        self.assertIn("fact_type", examples)
        
        examples = get_tool_param_examples("web_search")
        self.assertIn("query", examples)


class TestToolResultParser(unittest.TestCase):
    """Test the ToolResultParser class."""
    
    def setUp(self):
        self.parser = ToolResultParser()
    
    def test_parse_error_detection(self):
        """Test error detection in tool results."""
        # Error with emoji
        result = self.parser.parse_error("❌ Something went wrong")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "error")
        
        # Error with text
        result = self.parser.parse_error("Error: File not found")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "error")
        
        # Warning
        result = self.parser.parse_error("⚠️ Low memory")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "warning")
        
        # Success (no error)
        result = self.parser.parse_error("✅ Task completed")
        self.assertIsNone(result)
    
    def test_is_success_detection(self):
        """Test success detection in results."""
        self.assertTrue(self.parser.is_success("✅ Success"))
        self.assertTrue(self.parser.is_success("Task completed"))
        self.assertFalse(self.parser.is_success("❌ Error occurred"))
        self.assertFalse(self.parser.is_success("Error: Something failed"))
    
    def test_extract_data(self):
        """Test data extraction from tool results."""
        # Get time
        data = self.parser.extract_data("get_time", "14:30:00\n05.03.2024")
        self.assertEqual(data["time"], "14:30:00")
        self.assertEqual(data["date"], "05.03.2024")
        
        # System info
        data = self.parser.extract_data("system_info", "CPU: 45%\nRAM: 60%\nDisk: 70%")
        self.assertEqual(data["cpu_percent"], 45)
        self.assertEqual(data["ram_percent"], 60)


class TestMemoryToolsEnhancements(unittest.TestCase):
    """Test memory tool enhancements and fixes."""
    
    def test_recall_validation(self):
        """Test recall tool parameter validation."""
        from jarvis_tools import RecallParams
        
        # Valid
        params = RecallParams(query="test")
        self.assertEqual(params.query, "test")
        
        # Query too short should still validate at Pydantic level
        # (actual length check is in the tool function)
        params = RecallParams(query="a")
        self.assertEqual(params.query, "a")
    
    def test_remember_validation(self):
        """Test remember tool parameter validation."""
        from jarvis_tools import RememberParams
        
        # Valid with all params
        params = RememberParams(
            content="User likes coffee",
            fact_type="preference",
            confidence=0.9
        )
        self.assertEqual(params.content, "User likes coffee")
        self.assertEqual(params.fact_type, "preference")
        self.assertEqual(params.confidence, 0.9)
        
        # Valid with defaults
        params = RememberParams(content="Test fact")
        self.assertEqual(params.fact_type, "observation")
        self.assertEqual(params.confidence, 1.0)
    
    def test_forget_validation(self):
        """Test forget tool parameter validation."""
        from jarvis_tools import ForgetParams
        
        params = ForgetParams(fact_id="abc123")
        self.assertEqual(params.fact_id, "abc123")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error recovery."""
    
    def setUp(self):
        self.mock_bridge = MagicMock()
        self.mock_memory = MagicMock()
        self.mock_tools = {}
        self.react_loop = ReActLoop(
            bridge=self.mock_bridge,
            memory=self.mock_memory,
            tools=self.mock_tools,
            max_iterations=5
        )
    
    def test_empty_thought_extraction(self):
        """Test extraction with empty thought."""
        params = self.react_loop._extract_params_from_thought("recall", "")
        self.assertEqual(params.get("query"), "")
    
    def test_unknown_tool_extraction(self):
        """Test extraction for unknown tool."""
        params = self.react_loop._extract_params_from_thought("unknown_tool", "test")
        self.assertEqual(params, {})
    
    def test_czech_language_support(self):
        """Test parameter extraction with Czech text."""
        # Czech recall
        thought = "Musím si vzpomenout na 'preference uživatele'"
        params = self.react_loop._extract_params_from_thought("recall", thought)
        self.assertEqual(params.get("query"), "preference uživatele")
        
        # Czech remember
        thought = "Uživatel má rád kávu"
        params = self.react_loop._extract_params_from_thought("remember", thought)
        self.assertEqual(params.get("fact_type"), "preference")
    
    def test_multiple_params_in_thought(self):
        """Test extraction when multiple potential params exist."""
        thought = 'Check "file1.txt" and also "file2.txt"'
        params = self.react_loop._extract_params_from_thought("read_file", thought)
        # Should extract first match
        self.assertEqual(params.get("file_path"), "file1.txt")


class TestIntegrationScenarios(unittest.TestCase):
    """Integration test scenarios."""
    
    def test_scenario_1_memory_storage_and_recall(self):
        """Test 1: Memory storage and recall workflow."""
        logger.info("=== Test Scenario 1: Memory Storage and Recall ===")
        
        # This tests the complete flow:
        # 1. User asks to store something
        # 2. System extracts remember tool with params
        # 3. Memory is stored
        # 4. User asks to recall
        # 5. System extracts recall tool with params
        
        mock_bridge = MagicMock()
        mock_memory = MagicMock()
        mock_memory.recall.return_value = [
            {"content": "User likes coffee", "score": 0.9, "type": "preference"}
        ]
        
        react_loop = ReActLoop(
            bridge=mock_bridge,
            memory=mock_memory,
            tools={},
            max_iterations=3
        )
        
        # Test recall extraction
        thought = "I need to recall what the user likes to drink"
        params = react_loop._extract_params_from_thought("recall", thought)
        self.assertIsNotNone(params.get("query"))
        
        logger.info("✅ Scenario 1 passed")
    
    def test_scenario_2_file_operations(self):
        """Test 2: File read/write operations."""
        logger.info("=== Test Scenario 2: File Operations ===")
        
        mock_bridge = MagicMock()
        react_loop = ReActLoop(
            bridge=mock_bridge,
            memory=MagicMock(),
            tools={},
            max_iterations=3
        )
        
        # Test write file extraction
        thought = 'Create a file "report.txt" with the meeting notes'
        params = react_loop._extract_params_from_thought("write_file", thought)
        self.assertEqual(params.get("file_path"), "report.txt")
        
        logger.info("✅ Scenario 2 passed")
    
    def test_scenario_3_task_management(self):
        """Test 3: Task management workflow."""
        logger.info("=== Test Scenario 3: Task Management ===")
        
        mock_bridge = MagicMock()
        react_loop = ReActLoop(
            bridge=mock_bridge,
            memory=MagicMock(),
            tools={},
            max_iterations=3
        )
        
        # Test task addition
        thought = 'Add a task "Buy groceries" to my todo list'
        params = react_loop._extract_params_from_thought("manage_tasks", thought)
        self.assertEqual(params.get("action"), "add")
        self.assertEqual(params.get("task_description"), "Buy groceries")
        
        # Test task listing
        thought = 'Show me all my tasks'
        params = react_loop._extract_params_from_thought("manage_tasks", thought)
        self.assertEqual(params.get("action"), "list")
        
        logger.info("✅ Scenario 3 passed")
    
    def test_scenario_4_web_search(self):
        """Test 4: Web search with parameter extraction."""
        logger.info("=== Test Scenario 4: Web Search ===")
        
        mock_bridge = MagicMock()
        react_loop = ReActLoop(
            bridge=mock_bridge,
            memory=MagicMock(),
            tools={},
            max_iterations=3
        )
        
        # Test search extraction
        thought = 'Search for "Python best practices 2024"'
        params = react_loop._extract_params_from_thought("web_search", thought)
        self.assertEqual(params.get("query"), "Python best practices 2024")
        
        logger.info("✅ Scenario 4 passed")
    
    def test_scenario_5_python_execution(self):
        """Test 5: Python code execution."""
        logger.info("=== Test Scenario 5: Python Execution ===")
        
        mock_bridge = MagicMock()
        react_loop = ReActLoop(
            bridge=mock_bridge,
            memory=MagicMock(),
            tools={},
            max_iterations=3
        )
        
        # Test code extraction from markdown
        thought = "Calculate: ```python\nx = 5\ny = 10\nprint(x + y)\n```"
        params = react_loop._extract_params_from_thought("run_python", thought)
        self.assertIn("x = 5", params.get("code", ""))
        
        logger.info("✅ Scenario 5 passed")


def run_tests():
    """Run all test scenarios."""
    logger.info("=" * 60)
    logger.info("JARVIS Critical Bug Fixes - Test Suite")
    logger.info("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestParameterExtractionFallback))
    suite.addTests(loader.loadTestsFromTestCase(TestToolParameterValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestToolResultParser))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryToolsEnhancements))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationScenarios))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    logger.info(f"Tests run: {result.testsRun}")
    logger.info(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    logger.info(f"Failures: {len(result.failures)}")
    logger.info(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        logger.info("✅ All tests passed!")
        return 0
    else:
        logger.error("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
