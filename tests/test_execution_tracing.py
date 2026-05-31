import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import pytest
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.outputs import LLMResult, Generation

from tradingagents.dataflows.utils import CURRENT_NODE_NAME
from webapp.backend.tracing_handler import TracingCallbackHandler
import webapp.backend.db as db

@pytest.mark.unit
class ExecutionTracingTests(unittest.TestCase):
    def setUp(self):
        # Create a temp file for test database
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.patchers = [
            patch("webapp.backend.db.DB_PATH", self.db_path),
            patch("db.DB_PATH", self.db_path, create=True)
        ]
        for p in self.patchers:
            p.start()
        # Initialize test database
        db.init_db()

    def tearDown(self):
        for p in self.patchers:
            try:
                p.stop()
            except Exception:
                pass
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_current_node_name_resolution(self):
        handler = TracingCallbackHandler(task_id="task-123", run_id="run-456")
        
        # Test default/fallback
        node_name = handler._get_node_name({})
        self.assertEqual(node_name, "System")
        
        # Test metadata fallback
        node_name_meta = handler._get_node_name({"metadata": {"langgraph_node": "agent_x"}})
        self.assertEqual(node_name_meta, "agent_x")
        
        # Test context var takes priority
        token = CURRENT_NODE_NAME.set("Market Analyst")
        try:
            node_name_ctx = handler._get_node_name({})
            self.assertEqual(node_name_ctx, "Market Analyst")
        finally:
            CURRENT_NODE_NAME.reset(token)

    def test_tool_node_mapping(self):
        handler = TracingCallbackHandler(task_id="task-123", run_id="run-456")
        
        for category, expected in [
            ("market", "Market Analyst"),
            ("social", "Social Analyst"),
            ("news", "News Analyst"),
            ("fundamentals", "Fundamentals Analyst"),
        ]:
            token = CURRENT_NODE_NAME.set(f"tools_{category}")
            try:
                node_name = handler._get_node_name({})
                self.assertEqual(node_name, expected)
            finally:
                CURRENT_NODE_NAME.reset(token)

    def test_llm_trace_logging(self):
        handler = TracingCallbackHandler(task_id="task-test-llm", run_id="run-test-llm")
        
        # Mock serialized and messages
        serialized = {"name": "ChatOpenAI"}
        messages = [[HumanMessage(content="Hello AI")]]
        run_id = "test-lc-run-id"
        
        # Start trace
        handler.on_chat_model_start(serialized, messages, run_id=run_id)
        
        # End trace
        response = LLMResult(generations=[[Generation(text="Hello Human", message=AIMessage(content="Hello Human"))]])
        handler.on_llm_end(response, run_id=run_id)
        
        # Verify in DB
        traces = db.get_task_traces("task-test-llm")
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["task_id"], "task-test-llm")
        self.assertEqual(trace["run_id"], "run-test-llm")
        self.assertEqual(trace["type"], "llm")
        self.assertEqual(trace["name"], "ChatOpenAI")
        self.assertIn("Hello AI", trace["input"])
        self.assertIn("Hello Human", trace["output"])

    def test_tool_trace_logging(self):
        handler = TracingCallbackHandler(task_id="task-test-tool", run_id="run-test-tool")
        
        serialized = {"name": "fetch_stock_news"}
        input_str = "AAPL"
        run_id = "test-tool-run-id"
        
        # Start trace
        handler.on_tool_start(serialized, input_str, run_id=run_id)
        
        # End trace successfully
        handler.on_tool_end("Mocked tool result here", run_id=run_id)
        
        # Verify in DB
        traces = db.get_task_traces("task-test-tool")
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["task_id"], "task-test-tool")
        self.assertEqual(trace["type"], "tool")
        self.assertEqual(trace["name"], "fetch_stock_news")
        self.assertEqual(trace["input"], "AAPL")
        self.assertEqual(trace["output"], "Mocked tool result here")

    def test_tool_error_logging(self):
        handler = TracingCallbackHandler(task_id="task-test-err", run_id="run-test-err")
        
        serialized = {"name": "fetch_stock_news"}
        input_str = "AAPL"
        run_id = "test-tool-run-id"
        
        # Start trace
        handler.on_tool_start(serialized, input_str, run_id=run_id)
        
        # End trace with error
        handler.on_tool_error(ValueError("API error"), run_id=run_id)
        
        # Verify in DB
        traces = db.get_task_traces("task-test-err")
        self.assertEqual(len(traces), 1)
        self.assertIn("ERROR: API error", traces[0]["output"])

    def test_cleanup_old_traces(self):
        # Insert a very old trace manually
        old_trace = {
            "id": "old-id",
            "task_id": "task-old",
            "run_id": "run-old",
            "node_name": "System",
            "type": "llm",
            "name": "OldLLM",
            "input": "input",
            "output": "output",
            "timestamp": "2020-01-01T00:00:00Z"
        }
        db.add_task_trace(old_trace)
        
        # Insert a recent trace
        recent_trace = {
            "id": "recent-id",
            "task_id": "task-recent",
            "run_id": "run-recent",
            "node_name": "System",
            "type": "llm",
            "name": "RecentLLM",
            "input": "input",
            "output": "output",
            "timestamp": "2026-05-31T09:00:00Z"
        }
        db.add_task_trace(recent_trace)
        
        # Run cleanup (with e.g. 7 days retention)
        db.cleanup_old_traces(days=7)
        
        # Verify old trace deleted, recent trace kept
        traces_old = db.get_task_traces("task-old")
        traces_recent = db.get_task_traces("task-recent")
        self.assertEqual(len(traces_old), 0)
        self.assertEqual(len(traces_recent), 1)

    def test_wrap_node_with_context_handles_runnable_and_callable(self):
        from tradingagents.graph.setup import wrap_node_with_context
        
        # 1. Test regular callable (function)
        called_fn = False
        def dummy_fn(state, *args, **kwargs):
            nonlocal called_fn
            called_fn = True
            return "fn_result"
            
        wrapped_fn = wrap_node_with_context("TestNode", dummy_fn)
        res_fn = wrapped_fn({"state_val": 1})
        self.assertTrue(called_fn)
        self.assertEqual(res_fn, "fn_result")
        
        # 2. Test Runnable (object with invoke method, but not callable)
        class DummyRunnable:
            def __init__(self):
                self.called_invoke = False
            def invoke(self, state, *args, **kwargs):
                self.called_invoke = True
                return "runnable_result"
                
        runnable_obj = DummyRunnable()
        wrapped_runnable = wrap_node_with_context("TestNodeRunnable", runnable_obj)
        res_runnable = wrapped_runnable({"state_val": 2})
        self.assertTrue(runnable_obj.called_invoke)
        self.assertEqual(res_runnable, "runnable_result")

if __name__ == "__main__":
    unittest.main()
