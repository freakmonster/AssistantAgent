"""提示词统一导出。

集中管理所有「纯文本提示词」（系统提示词、摘要压缩等）。
工具描述（docstring）不在此列，需保留在各自工具函数上，因 LangChain 的
`@tool` 装饰器依赖 docstring 生成工具描述与参数 schema。
"""
from app.prompts.check import build_check_drift_prompt
from app.prompts.system import SYSTEM_PROMPT
from app.prompts.summarize import build_summarize_prompt

__all__ = ["SYSTEM_PROMPT", "build_summarize_prompt", "build_check_drift_prompt"]
