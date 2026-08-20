"""文件附件压缩提示词。

供 file_compress 服务调用，将超长解析文本交给 LLM 做忠实语义压缩，
保留关键事实与结构，输出到目标长度以内。
"""

_COMPRESS_INSTRUCTION = (
    "你是文档压缩助手。请将下面的文档内容忠实压缩，不得编造、不得添加原文没有的信息。\n"
    "要求（按优先级从高到低）：\n"
    "- 保真优先：人名、数字、日期、金额、结论、步骤、待办、关键约束等必须原样保留，"
    "宁可输出略长，也不删减关键信息或改动数字\n"
    "- 若原文为表格或键值数据，保持其键值/行列对应关系，不要改写为散文\n"
    "- 使用 Markdown（标题、列表、表格）尽量保持原文结构\n"
    "- 长度尽量控制在约 {target_chars} 字符以内，但不强制，保真与结构优先于长度\n"
    "- 只输出压缩后的正文，不要输出任何解释或前言\n\n"
)

_CHUNK_PREFIX_TEMPLATE = "（本片为第 {chunk_index}/{chunk_total} 片，仅提炼本片关键内容，不要引入其他片内容）\n\n"

_DOCUMENT_TEMPLATE = "待压缩的文档内容：\n{text}"


def build_file_compress_prompt(
    text: str,
    target_chars: int,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
) -> str:
    """组装文件压缩的完整提示词。

    Args:
        text: 待压缩的文档文本（或分片后的一片文本）。
        target_chars: 目标压缩长度（字符）。
        chunk_index: 分片序号（1 起），单次压缩时为 None。
        chunk_total: 分片总数，单次压缩时为 None。

    Returns:
        完整的压缩提示词。
    """
    prompt = _COMPRESS_INSTRUCTION.format(target_chars=target_chars)
    if chunk_index is not None and chunk_total is not None:
        prompt += _CHUNK_PREFIX_TEMPLATE.format(
            chunk_index=chunk_index, chunk_total=chunk_total
        )
    prompt += _DOCUMENT_TEMPLATE.format(text=text)
    return prompt