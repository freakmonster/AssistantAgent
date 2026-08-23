"""影刀 RPA 热键触发服务。

通过 ctypes SendInput 模拟系统级键盘事件（进入系统输入队列），触发影刀客户端的
全局热键（影刀原生「热键触发」机制），从而拉起指定的 RPA 应用。

使用 SendInput 而非 SendKeys 的原因：SendKeys 只发送给前台窗口，无法触发全局热键；
SendInput 注入的是系统级事件，可被影刀客户端的全局热键钩子识别。

前置条件：
1. 影刀客户端须保持运行，且目标应用已配置热键触发
2. 本服务运行在用户交互桌面会话（Session 0 隔离环境下 SendInput 无效）
3. 热键映射通过配置项 YINGDAO_RPA_HOTKEYS 注入（{"应用名": "热键组合"}）
"""
import ctypes
import json
import logging
import subprocess
import time
from ctypes import wintypes

from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Windows 常量 ---
INPUT_KEYBOARD = 1  # SendInput 事件类型：键盘
KEYEVENTF_KEYUP = 0x0002  # 按键抬起标志
# 虚拟键码（修饰键 + 常见主键）
_VK_MAP: dict[str, int] = {
    "ctrl": 0x11,   # VK_CONTROL
    "control": 0x11,
    "shift": 0x10,  # VK_SHIFT
    "alt": 0x12,    # VK_MENU
    "win": 0x5B,    # VK_LWIN
    "meta": 0x5B,
}
_VK_MAP.update({f"f{i}": 0x6F + i for i in range(1, 13)})  # F1-F12
_VK_MAP.update({str(d): 0x30 + d for d in range(10)})  # 数字键 0-9
_VK_MAP.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})  # A-Z（字母键 VK 码为大写 ASCII）
_VK_MAP.update({chr(c): c - 0x20 for c in range(ord("a"), ord("z") + 1)})  # 小写字母映射到同键大写 VK 码

# 修饰键集合：配置中先出现的修饰键在按下阶段先按下、抬起阶段后释放
_MODIFIERS = {"ctrl", "control", "shift", "alt", "win", "meta"}

# --- 结构体定义（32/64 位兼容） ---
# ULONG_PTR：64 位下为 8 字节无符号整数，32 位下为 4 字节
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    """鼠标输入结构（仅用于对齐 INPUT 联合体大小）。"""
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    """键盘输入结构。"""
    _fields_ = [
        ("wVk", wintypes.WORD),  # 虚拟键码
        ("wScan", wintypes.WORD),  # 硬件扫描码
        ("dwFlags", wintypes.DWORD),  # 事件标志
        ("time", wintypes.DWORD),  # 时间戳
        ("dwExtraInfo", ULONG_PTR),  # 附加信息
    ]


class HARDWAREINPUT(ctypes.Structure):
    """硬件输入结构（仅用于对齐 INPUT 联合体大小）。"""
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    """INPUT 联合体：键盘/鼠标/硬件三种输入。"""
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """SendInput 的输入事件结构。"""
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),  # 事件类型
        ("u", INPUTUNION),
    ]


def parse_hotkey(hotkey_str: str) -> list[int]:
    """解析热键组合字符串为虚拟键码序列。

    Args:
        hotkey_str: 热键组合，如 "ctrl+shift+alt+c"（+ 分隔，大小写不敏感）。

    Returns:
        虚拟键码列表，修饰键在前、主键在后（按下顺序）。

    Raises:
        ValueError: 热键格式非法（空、未知键名、缺少主键）。
    """
    tokens = [t.strip().lower() for t in hotkey_str.split("+") if t.strip()]
    if not tokens:
        raise ValueError(f"热键为空: {hotkey_str!r}")
    vk_codes = []
    for token in tokens:
        vk = _VK_MAP.get(token)
        if vk is None:
            raise ValueError(f"不支持的热键键名: {token}")
        vk_codes.append(vk)
    # 主键必须是最后一个 token，且不能是修饰键（避免只有修饰键无主键）
    if tokens[-1] in _MODIFIERS:
        raise ValueError(f"热键缺少主键: {hotkey_str!r}")
    return vk_codes


def _build_key_event(vk: int, flags: int = 0) -> INPUT:
    """构造单个键盘输入事件。"""
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = 0
    inp.ki.dwFlags = flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = 0
    return inp


def send_key_combo(vk_codes: list[int], pause_ms: int = 50) -> bool:
    """注入键盘组合事件（按下→停顿→反序抬起），返回是否全部事件注入成功。

    Args:
        vk_codes: 虚拟键码列表（按下顺序，修饰键在前）。
        pause_ms: 按下与抬起之间的停顿毫秒数，确保热键钩子识别完整组合。

    Returns:
        True 表示全部事件注入成功（注入数 == 2 * len(vk_codes)）。
    """
    down = [_build_key_event(vk) for vk in vk_codes]
    up = [_build_key_event(vk, KEYEVENTF_KEYUP) for vk in reversed(vk_codes)]
    send_input = ctypes.windll.user32.SendInput
    send_input.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    send_input.restype = wintypes.UINT

    total = 0
    for events in (down, up):
        array = (INPUT * len(events))(*events)
        total += send_input(len(array), array, ctypes.sizeof(INPUT))
        time.sleep(pause_ms / 1000)
    return total == 2 * len(vk_codes)


def is_shadowbot_running() -> bool:
    """探测影刀客户端是否在运行（主进程为 ShadowBot.Shell.exe，早期版本为 ShadowBot.exe）。"""
    try:
        # Windows 自带 tasklist（无第三方依赖）
        # 中文系统 tasklist 输出为 GBK 编码，需显式解码避免 UTF-8 解码失败
        result = subprocess.run(
            ["tasklist", "/NH"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        stdout = result.stdout.decode("gbk", errors="ignore")
        return "ShadowBot.Shell.exe" in stdout or "ShadowBot.exe" in stdout
    except Exception as exc:  # noqa: BLE001 - 探测失败时保守返回 False 并记录日志
        logger.warning("探测影刀客户端进程失败: %s", exc)
        return False


def trigger_rpa_app(app_name: str) -> str:
    """通过热键触发指定影刀 RPA 应用，返回结构化 JSON 字符串。

    Args:
        app_name: 影刀 RPA 应用名称（须与配置 YINGDAO_RPA_HOTKEYS 的 key 一致）。

    Returns:
        JSON 字符串：{"success": true, "message": ..., "hotkey": ..., "app_name": ...}
        或错误结构 {"error": ..., "message": ...}。
    """
    hotkeys = settings.rpa_hotkeys
    if not hotkeys:
        return json.dumps(
            {
                "error": "not_configured",
                "message": "未配置影刀 RPA 热键映射（YINGDAO_RPA_HOTKEYS）",
            },
            ensure_ascii=False,
        )

    hotkey = hotkeys.get(app_name)
    if hotkey is None:
        return json.dumps(
            {
                "error": "app_not_found",
                "message": f"未配置应用「{app_name}」的热键触发，可用的应用：{list(hotkeys.keys())}",
                "available_apps": list(hotkeys.keys()),
            },
            ensure_ascii=False,
        )

    if not is_shadowbot_running():
        return json.dumps(
            {
                "error": "client_offline",
                "message": "影刀客户端未运行，请先打开影刀客户端再重试",
            },
            ensure_ascii=False,
        )

    try:
        vk_codes = parse_hotkey(hotkey)
    except ValueError as exc:
        return json.dumps(
            {"error": "config_error", "message": f"热键配置非法：{exc}"},
            ensure_ascii=False,
        )

    injected = send_key_combo(vk_codes)
    if not injected:
        logger.error("热键注入失败 app=%s hotkey=%s", app_name, hotkey)
        return json.dumps(
            {
                "error": "inject_failed",
                "message": "热键注入失败，请检查影刀客户端热键是否被其他软件占用",
            },
            ensure_ascii=False,
        )

    logger.info("已通过热键触发影刀应用 app=%s hotkey=%s", app_name, hotkey)
    return json.dumps(
        {
            "success": True,
            "message": f"已通过热键 {hotkey.upper()} 触发「{app_name}」，正在后台运行。"
            f"可打开影刀客户端任务面板查看实时进度。",
            "hotkey": hotkey,
            "app_name": app_name,
        },
        ensure_ascii=False,
    )
