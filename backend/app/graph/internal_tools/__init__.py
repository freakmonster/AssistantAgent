"""内部工具聚合入口。

每个内部工具独立一个文件（如 image_cogview_3_flash.py），本模块统一导入
并导出 INTERNAL_TOOLS 列表，供 agent.py 注册到 MCPHost。

现有历史工具仍保留在 tools.py，通过这里一并聚合，保持注册契约不变。
"""
from app.graph.tools import INTERNAL_TOOLS as _LEGACY_INTERNAL_TOOLS
from app.graph.internal_tools.image_cogview_3_flash import generate_image

# 现有工具 + 新增工具，导出列表名与 tools.py 保持一致
INTERNAL_TOOLS = [*_LEGACY_INTERNAL_TOOLS, generate_image]


__all__ = ["INTERNAL_TOOLS"]
