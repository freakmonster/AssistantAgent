"""文件系统 MCP Server（自建 stdio 示例）。

由主应用通过 stdio 作为子进程拉起（见 services/mcp/server_config.py 的
build_filesystem_server），暴露受限的文件读取工具。

权限边界：所有路径操作强制限制在环境变量 ALLOWED_ROOT 目录内，
越界访问会被拒绝并返回结构化错误 JSON（不抛异常），
与主应用 call_tool 的工具错误约定保持一致。
"""
import json
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("filesystem")


def _error(error: str, message: str) -> str:
    """构造结构化错误 JSON 字符串。

    与 AGENTS.md 约定的工具错误格式一致：{"error": "...", "message": "..."}。
    """
    return json.dumps({"error": error, "message": message}, ensure_ascii=False)


def _resolve_within_root(path: str) -> str:
    """把用户传入的路径解析为 ALLOWED_ROOT 内的绝对路径，并校验越界。

    越界校验流程：
    1. 读取环境变量 ALLOWED_ROOT 作为允许访问的根目录。
    2. 用 os.path.realpath 同时消解 `..`、`.` 和符号链接，得到真实路径。
    3. 判断真实路径是否等于根目录、或以「根目录 + 路径分隔符」为前缀；
       若不是，则说明用户试图逃逸到根目录之外。

    返回：
        合法的绝对路径字符串。

    抛出：
        ValueError：路径为空、或解析后越界时（异常信息为给用户的友好中文说明）。
    """
    root = os.environ["ALLOWED_ROOT"]
    real_root = os.path.realpath(root)

    if not path:
        raise ValueError("路径为空")

    full = os.path.realpath(os.path.join(root, path))
    if full != real_root and not full.startswith(real_root + os.sep):
        raise ValueError(f"路径越界：{path} 不在允许目录 {root} 内")
    return full


@mcp.tool()
async def read_file(path: str) -> str:
    """读取指定文本文件内容。

    适用场景：读取 ALLOWED_ROOT 目录内的文本文件。
    不适用场景：二进制文件、目录、越界路径。

    Args:
        path: 相对于 ALLOWED_ROOT 的文件路径。

    Returns:
        成功时返回文件文本内容。
        失败时返回结构化错误 JSON 字符串，例如：

        - 路径越界（访问 ALLOWED_ROOT 之外的文件）时返回：
          {"error": "PathTraversal",
           "message": "路径越界：../../etc/passwd 不在允许目录 /data/uploads 内"}

        - 文件不存在时返回：
          {"error": "NotFound", "message": "文件不存在或不是普通文件：xxx"}

        - 读取失败时返回：
          {"error": "ReadError", "message": "读取失败：<OS 错误信息>"}
    """
    try:
        full = _resolve_within_root(path)
    except ValueError as exc:
        return _error("PathTraversal", str(exc))

    if not os.path.isfile(full):
        return _error("NotFound", f"文件不存在或不是普通文件：{path}")

    try:
        with open(full, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        return _error("ReadError", f"读取失败：{exc}")
