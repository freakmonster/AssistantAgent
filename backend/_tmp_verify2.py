"""临时验证：json.dumps(default=str) 对 ToolMessage 的实际序列化形态。"""
import json

from langchain_core.messages import ToolMessage

m = ToolMessage(
    content='{"type":"task","task_id":"abc123","status":"running"}',
    tool_call_id="t1",
    name="submit_task",
)
print("--- str ---")
print(json.dumps({"tools": {"messages": [m]}}, default=str))
print("--- model_dump ---")
print(json.dumps({"tools": {"messages": [m.model_dump()]}}, default=str))
