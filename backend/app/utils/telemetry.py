"""OpenTelemetry 初始化与 tracer 获取。

配置 TracerProvider 与导出器（OTLP/Jaeger 或控制台降级），
暴露全局 tracer 供 agent_node / tool_node / MCP 工具调用手动埋点。
"""
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.core.config import settings

# 服务资源标识（在 Trace 后端中显示 service.name）
_resource = Resource.create({"service.name": settings.SERVICE_NAME})

_provider = TracerProvider(resource=_resource)

# 未配置 OTLP 端点时降级为控制台导出，保证本地无 Jaeger 也能看到 span
if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
    _exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
else:
    _exporter = ConsoleSpanExporter()

_provider.add_span_processor(BatchSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)

# 全局 tracer，供各节点手动埋点使用
tracer = trace.get_tracer(settings.SERVICE_NAME)
