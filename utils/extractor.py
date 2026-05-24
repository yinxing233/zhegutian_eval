# src/utils/extractor.py
"""
extract_ci_text: GLM 专用兼容垫片（从 self_explanation 中提取正文）
"""


def extract_ci_text(text: str) -> str:
    """
    GLM 专用：从 raw_output 中提取纯词作正文。
    GLM 的输出协议：final_answer + self_explanation
    利用排版惯性（空行分段）区分正文块和元文本块。
    只在 provider == "glm" 时调用，不污染其他 provider 路径。
    """
    text = text.strip()
    if not text:
        return ""

    # 按空行分块——GLM 的正文和解析之间有稳定空行
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        return text

    poem_blocks = []

    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue

        block_text = " ".join(lines)

        # 元文本触发词：通常出现在解析/说明段落开头
        meta_starts = [
            "格律",
            "说明",
            "解析",
            "注释",
            "创作",
            "押韵",
            "平仄",
            "韵脚",
            "要求",
            "符合",
            "本词",
            "整首词",
            "这首词",
            "此词",
            "好的",
            "以下",
            "---",
            "**",
            "注：",
            "注:",
        ]
        is_meta = any(block_text.startswith(kw) for kw in meta_starts)

        # 单行超长且无诗句标点 → 大概率是压平的说明文本
        if not is_meta and len(lines) == 1 and len(lines[0]) > 35:
            if not any(kw in lines[0] for kw in ["鹧鸪天", "·", "，", "。"]):
                is_meta = True

        if not is_meta:
            poem_blocks.append(block)

    result = "\n\n".join(poem_blocks).strip()

    # 如果全被过滤了，返回空（让下游 evaluator 的 empty_output 标签接手）
    if not result or len(result) < 10:
        return ""

    return result
