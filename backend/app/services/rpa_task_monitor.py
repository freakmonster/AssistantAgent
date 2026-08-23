"""影刀 RPA 任务状态监控服务。

影刀客户端不对外回传应用执行状态，本模块通过增量解析影刀「主日志」
（C:/Users/<用户>/AppData/Local/ShadowBot/log/{YYYYMMDD}.log）判定任务状态。

主日志任务生命周期关键行（实测格式）：
- 入队:   task continue: True. <应用名> <uuid> <触发方式>
- 启动:   robot task <应用名> started
- 退出码: xbot engine exited, pid:xxx, engineid:N, exitCode:0|1|-1
- 结束:   task end <应用名>, taskName:xxx, s26, window closed

判定状态机：UNKNOWN → ENQUEUED → RUNNING → SUCCESS / FAILED；超时兜底 TIMEOUT。
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.services.rpa_hotkey import is_shadowbot_running

logger = logging.getLogger(__name__)

# 日志行时间戳前缀：2026-08-22 18:00:15,056
_TS_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
# 错误行（日志级别为 ERROR）
_ERROR_PATTERN = re.compile(r"\[ERROR\]")
# 引擎退出码（串行执行下归属目标任务；pid/engineid 后逗号与空格格式不固定）
_EXIT_CODE_PATTERN = re.compile(r"xbot engine exited, pid:\d+\s*,\s*engineid:\d+\s*,\s*exitCode:(-?\d+)")

# 状态枚举
STATE_UNKNOWN = "UNKNOWN"
STATE_ENQUEUED = "ENQUEUED"
STATE_RUNNING = "RUNNING"
STATE_SUCCESS = "SUCCESS"
STATE_FAILED = "FAILED"
STATE_TIMEOUT = "TIMEOUT"
STATE_CLIENT_OFFLINE = "CLIENT_OFFLINE"


def get_log_dir() -> Path:
    """返回影刀日志目录（可用配置 YINGDAO_RPA_LOG_DIR 覆盖默认路径）。"""
    if settings.YINGDAO_RPA_LOG_DIR:
        return Path(settings.YINGDAO_RPA_LOG_DIR)
    return Path.home() / "AppData" / "Local" / "ShadowBot" / "log"


def _iter_relevant_lines(app_name: str, trigger_time: datetime) -> list[str]:
    """读取触发时间之后的主日志行（跨天时合并当天与次日文件，按时间戳过滤）。

    影刀任务为单引擎串行执行，日志按时间顺序追加；跨 0 点时日志切换到新日期文件，
    因此同时扫描 trigger_time 所在日与当前日两个文件，按时间戳过滤去重。
    """
    log_dir = get_log_dir()
    dates = {trigger_time.date(), datetime.now().date()}
    lines: list[str] = []
    for date in sorted(dates):
        log_file = log_dir / f"{date:%Y%m%d}.log"
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("读取影刀主日志失败: %s", exc)
            continue
        for raw in content.splitlines():
            line = raw.strip()
            m = _TS_PATTERN.match(line)
            if not m:
                continue
            try:
                line_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f")
            except ValueError:
                continue
            if line_ts >= trigger_time:
                lines.append(line)
    # 按时间戳排序去重（两份文件可能同时含同一行）
    seen: set[str] = set()
    ordered: list[str] = []
    for line in sorted(lines, key=lambda s: s[:23]):
        if line not in seen:
            seen.add(line)
            ordered.append(line)
    return ordered


def check_rpa_task_status(app_name: str, trigger_time: datetime) -> dict:
    """增量解析主日志，判定指定应用的最近一次触发任务状态。

    Args:
        app_name: 影刀 RPA 应用名称。
        trigger_time: 热键触发时间（用于定位日志区间）。

    Returns:
        状态字典：{"state", "app_name", "trigger_time", "elapsed", "exit_code", "detail"}。
    """
    elapsed = (datetime.now() - trigger_time).total_seconds()
    timeout = settings.YINGDAO_RPA_STATUS_TIMEOUT

    # 与应用绑定的匹配规则（re.escape 防止应用名中的特殊字符破坏正则）
    escaped = re.escape(app_name)
    enqueued_re = re.compile(rf"task continue: True\. {escaped} |new task appName:{escaped}")
    started_re = re.compile(rf"robot task {escaped} started")
    finished_re = re.compile(rf"task end {escaped}, taskName:.*?window closed")

    enqueued = False
    running = False
    finished = False
    exit_code: int | None = None
    error_msg: str | None = None

    for line in _iter_relevant_lines(app_name, trigger_time):
        # 目标任务已结束：后续行属于其他任务，停止扫描避免跨任务污染
        if finished_re.search(line):
            finished = True
            break
        if _ERROR_PATTERN.search(line) and error_msg is None:
            error_msg = line[:200]
        if enqueued_re.search(line):
            enqueued = True
        if started_re.search(line):
            running = True
        # 退出码仅在目标任务启动后采集（running 窗口内）
        if running:
            m = _EXIT_CODE_PATTERN.search(line)
            if m:
                exit_code = int(m.group(1))

    # 状态判定（优先级：结束 → 非零退出码 → 运行中 → 入队 → 超时/未知）
    if finished:
        if exit_code in (0, None):
            state, detail = STATE_SUCCESS, "任务正常结束"
        else:
            state, detail = STATE_FAILED, f"任务执行失败（exitCode={exit_code}）"
    elif exit_code is not None and exit_code != 0:
        state, detail = STATE_FAILED, f"任务执行失败（exitCode={exit_code}）"
    elif running:
        state, detail = STATE_RUNNING, "任务正在执行中"
    elif enqueued:
        state, detail = STATE_ENQUEUED, "任务已进入执行队列"
    elif elapsed >= timeout:
        state, detail = STATE_TIMEOUT, f"超过 {int(timeout)}s 未检测到任务启动，可能未执行"
    else:
        state, detail = STATE_UNKNOWN, "尚未检测到任务记录"

    # 客户端离线兜底（仅当任务未正常结束时检查）
    if state in (STATE_UNKNOWN, STATE_TIMEOUT, STATE_ENQUEUED) and not is_shadowbot_running():
        state, detail = STATE_CLIENT_OFFLINE, "影刀客户端未运行"

    if state == STATE_FAILED and error_msg:
        detail = f"{detail}；错误信息：{error_msg}"

    return {
        "state": state,
        "app_name": app_name,
        "trigger_time": trigger_time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed": int(elapsed),
        "exit_code": exit_code,
        "detail": detail,
    }


def check_rpa_task_status_json(app_name: str, trigger_time_str: str) -> str:
    """check_rpa_task_status 的 JSON 字符串封装（供工具层调用）。

    Args:
        app_name: 影刀 RPA 应用名称。
        trigger_time_str: 触发时间（ISO 格式，如 "2026-08-22 18:00:15"）。

    Returns:
        状态 JSON 字符串。
    """
    try:
        trigger_time = datetime.fromisoformat(trigger_time_str.strip())
    except (ValueError, AttributeError) as exc:
        return json.dumps(
            {"error": "invalid_trigger_time", "message": f"触发时间格式非法：{exc}，示例：2026-08-22 18:00:15"},
            ensure_ascii=False,
        )
    # 兼容无时区的 ISO 字符串；含时区时转本地时间
    if trigger_time.tzinfo is not None:
        trigger_time = trigger_time.astimezone().replace(tzinfo=None)
    return json.dumps(check_rpa_task_status(app_name, trigger_time), ensure_ascii=False)
