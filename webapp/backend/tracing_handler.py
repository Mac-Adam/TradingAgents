import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


class TracingCallbackHandler(BaseCallbackHandler):
    """Callback handler that traces every single LLM and tool invocation."""

    def __init__(self, task_id: str, run_id: str):
        super().__init__()
        self.task_id = task_id
        self.run_id = run_id
        self.active_runs = {}

    def _get_node_name(self, kwargs: Any) -> str:
        """Resolve the active agent/node name."""
        from tradingagents.dataflows.utils import CURRENT_NODE_NAME
        node_name = CURRENT_NODE_NAME.get()
        if not node_name:
            node_name = kwargs.get("metadata", {}).get("langgraph_node")
        if not node_name:
            node_name = "System"

        # Map tools node to its parent analyst agent for cleaner grouping
        if node_name.startswith("tools_"):
            category = node_name.split("_")[1]
            if category == "market":
                node_name = "Market Analyst"
            elif category == "social":
                node_name = "Social Analyst"
            elif category == "news":
                node_name = "News Analyst"
            elif category == "fundamentals":
                node_name = "Fundamentals Analyst"
        return node_name

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        **kwargs: Any,
    ) -> None:
        node_name = self._get_node_name(kwargs)
        flat_messages = []
        for msg_list in messages:
            for m in msg_list:
                if isinstance(m, BaseMessage):
                    # Handle message properties cleanly
                    msg_dict = {
                        "role": m.type,
                        "content": m.content,
                    }
                    if hasattr(m, "additional_kwargs") and m.additional_kwargs:
                        msg_dict["additional_kwargs"] = m.additional_kwargs
                    flat_messages.append(msg_dict)
                else:
                    flat_messages.append({
                        "role": getattr(m, "type", "unknown"),
                        "content": str(m)
                    })

        run_id_lc = str(kwargs.get("run_id") or uuid.uuid4())
        self.active_runs[run_id_lc] = {
            "type": "llm",
            "name": serialized.get("name") or "LLM",
            "node_name": node_name,
            "input": json.dumps(flat_messages),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        node_name = self._get_node_name(kwargs)
        run_id_lc = str(kwargs.get("run_id") or uuid.uuid4())
        self.active_runs[run_id_lc] = {
            "type": "llm",
            "name": serialized.get("name") or "LLM",
            "node_name": node_name,
            "input": json.dumps(prompts),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        run_id_lc = str(kwargs.get("run_id"))
        if run_id_lc not in self.active_runs:
            return

        start_info = self.active_runs.pop(run_id_lc)
        outputs = []
        try:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    if msg and isinstance(msg, BaseMessage):
                        gen_info = {
                            "content": msg.content
                        }
                        # Include tool calls if present
                        tool_calls = getattr(msg, "tool_calls", []) or msg.additional_kwargs.get("tool_calls")
                        if tool_calls:
                            # Handle converting tool call objects to JSON-safe lists
                            safe_calls = []
                            for tc in tool_calls:
                                if isinstance(tc, dict):
                                    safe_calls.append(tc)
                                else:
                                    safe_calls.append({
                                        "name": getattr(tc, "name", ""),
                                        "args": getattr(tc, "args", {}),
                                        "id": getattr(tc, "id", None)
                                    })
                            gen_info["tool_calls"] = safe_calls
                        outputs.append(gen_info)
                    else:
                        outputs.append({
                            "content": gen.text
                        })
        except Exception as e:
            outputs = [{"error": f"Failed to extract outputs: {str(e)}"}]

        import db
        db.add_task_trace({
            "id": str(uuid.uuid4()),
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_name": start_info["node_name"],
            "type": "llm",
            "name": start_info["name"],
            "input": start_info["input"],
            "output": json.dumps(outputs),
            "timestamp": start_info["timestamp"]
        })

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        node_name = self._get_node_name(kwargs)
        run_id_lc = str(kwargs.get("run_id") or uuid.uuid4())
        self.active_runs[run_id_lc] = {
            "type": "tool",
            "name": serialized.get("name") or "Tool",
            "node_name": node_name,
            "input": input_str,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        run_id_lc = str(kwargs.get("run_id"))
        if run_id_lc not in self.active_runs:
            return

        start_info = self.active_runs.pop(run_id_lc)

        import db
        db.add_task_trace({
            "id": str(uuid.uuid4()),
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_name": start_info["node_name"],
            "type": "tool",
            "name": start_info["name"],
            "input": start_info["input"],
            "output": str(output),
            "timestamp": start_info["timestamp"]
        })

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        run_id_lc = str(kwargs.get("run_id"))
        if run_id_lc not in self.active_runs:
            return

        start_info = self.active_runs.pop(run_id_lc)

        import db
        db.add_task_trace({
            "id": str(uuid.uuid4()),
            "task_id": self.task_id,
            "run_id": self.run_id,
            "node_name": start_info["node_name"],
            "type": "tool",
            "name": start_info["name"],
            "input": start_info["input"],
            "output": f"ERROR: {str(error)}",
            "timestamp": start_info["timestamp"]
        })
