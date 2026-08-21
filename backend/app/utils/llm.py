"""LLM 实例工厂与模型路由。

集中构建 ChatOpenAI 实例，供主推理/复核/摘要/压缩等各场景复用，避免各处硬编码
模型 id 与密钥。模型路由按配置建立「模型 id -> 供应商端点/密钥」映射，前端选择的
模型 id 在此解析为对应供应商的 ChatOpenAI 实例（带实例缓存）。
"""
import json
import os
import re
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from app.core.config import settings


def build_chat_llm(
    model: str,
    api_key: str,
    base_url: str,
    temperature: float = 0,
) -> ChatOpenAI:
    """按参数构建 ChatOpenAI 实例。

    Args:
        model: 模型 id（如 deepseek-chat / deepseek-flash）。
        api_key: API 密钥。
        base_url: API 端点。
        temperature: 采样温度，默认 0 以保证摘要/压缩结果稳定。

    Returns:
        配置好的 ChatOpenAI 实例。
    """
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )


@dataclass(frozen=True)
class ModelRoute:
    """一条模型路由：模型 id 及展示名、供应商端点与密钥。

    base_url/api_key 为空字符串表示回退 DEEPSEEK_BASE_URL/DEEPSEEK_API_KEY。
    fallback 为备用模型 id，留空时降级回退 DEFAULT_MODEL。
    """

    id: str
    name: str
    base_url: str
    api_key: str
    fallback: str = ""
    hidden: bool = False  # 为 True 时不暴露给前端模型列表（仅后端内部可用，如备用模型）


# 未配置 MODEL_ROUTES 时的默认路由：DeepSeek 两档，端点与密钥按需回退
_DEFAULT_ROUTES: tuple[dict, ...] = (
    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "base_url": "", "api_key": ""},
    {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "base_url": "", "api_key": ""},
)


def get_model_routes() -> list[ModelRoute]:
    """解析配置，返回模型路由列表（含 base_url/api_key，仅内部使用）。"""
    raw = settings.MODEL_ROUTES.strip()
    if not raw:
        routes: list = list(_DEFAULT_ROUTES)
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"MODEL_ROUTES 配置不是合法 JSON：{exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("MODEL_ROUTES 配置必须是 JSON 数组")
        routes = parsed

    result: list[ModelRoute] = []
    for item in routes:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        name = item.get("name")
        if not model_id or not name:
            continue
        result.append(
            ModelRoute(
                id=str(model_id),
                name=str(name),
                base_url=str(item.get("base_url") or ""),
                api_key=str(item.get("api_key") or ""),
                fallback=str(item.get("fallback") or ""),
                hidden=bool(item.get("hidden") or False),
            )
        )
    return result


def list_available_models() -> list[dict]:
    """对外返回可选模型列表（仅 id + name，不暴露密钥）。"""
    return [{"id": r.id, "name": r.name} for r in get_model_routes() if not r.hidden]


def resolve_model(model_id: str | None) -> ModelRoute:
    """按 id 解析模型路由；未指定时回退默认模型，找不到抛 ValueError。"""
    target = model_id or settings.DEFAULT_MODEL
    for route in get_model_routes():
        if route.id == target:
            return route
    raise ValueError(f"未知模型：{target}")


def resolve_model_fallback(model_id: str) -> str | None:
    """返回该模型的备用模型 id；未显式配置时回退 DEFAULT_MODEL，且不与主模型相同。

    Args:
        model_id: 主模型 id。

    Returns:
        备用模型 id；无可用备用模型时返回 None。
    """
    route = resolve_model(model_id)
    fallback = route.fallback or settings.DEFAULT_MODEL
    if fallback and fallback != route.id:
        return fallback
    return None


# 匹配 @VAR 占位符，用于在路由 base_url/api_key 中引用 settings 已有字段。
# 说明：不采用 ${VAR}，因为 pydantic-settings/dotenv 加载 .env 时会自动插值 ${VAR}，
# 且仅能引用更早定义或 os.environ 中的变量，跨行引用会被展开为空。
_ENV_REF_RE = re.compile(r"@(\w+)")


def _expand_env_ref(value: str) -> str:
    """展开 ``@VAR`` 占位符：优先取 settings 字段，其次环境变量，取不到则原样保留。"""
    def _repl(match: re.Match) -> str:
        key = match.group(1)
        field = getattr(settings, key, None)
        if field is not None:
            return str(field)
        return os.environ.get(key, match.group(0))

    return _ENV_REF_RE.sub(_repl, value)


# 模型实例缓存：同一模型 id 只构建一次，避免每个 agent 步骤重复创建
_llm_cache: dict[str, ChatOpenAI] = {}


def build_llm_for_model(model_id: str | None) -> ChatOpenAI:
    """按模型路由构建（缓存）ChatOpenAI 实例。

    Args:
        model_id: 模型 id；None 时回退默认模型。

    Returns:
        ChatOpenAI 实例（温度 0，保证主推理输出稳定）。
    """
    route = resolve_model(model_id)
    cached = _llm_cache.get(route.id)
    if cached is not None:
        return cached
    base_url = _expand_env_ref(route.base_url) or settings.DEEPSEEK_BASE_URL
    api_key = _expand_env_ref(route.api_key) or settings.DEEPSEEK_API_KEY
    llm = build_chat_llm(route.id, api_key, base_url, temperature=0)
    _llm_cache[route.id] = llm
    return llm