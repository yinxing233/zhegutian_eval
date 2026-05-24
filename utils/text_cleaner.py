"""
统一文本清洗工具
MVP 版本：做最小必要处理，保证产出干净的正文
"""

import unicodedata


def clean_text(text: str) -> str:
    """统一清洗生成文本，消除协议污染"""
    if text is None:
        return ""

    # 1. 首尾空白
    text = text.strip()
    if not text:
        return ""

    # 2. Unicode NFKC 归一化
    text = unicodedata.normalize("NFKC", text)

    # 3. 删除末尾的 [END]（允许后面跟空白）
    if text.rstrip().endswith("[END]"):
        text = text.rstrip()[:-5].strip()

    # 4. 压缩首尾多余空行，保留内部最多一个连续空行
    lines = text.splitlines()
    # 去除开头和结尾的空行
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()

    cleaned = []
    prev_empty = False
    for line in lines:
        if line.strip() == "":
            if not prev_empty:
                cleaned.append("")
                prev_empty = True
        else:
            cleaned.append(line)
            prev_empty = False

    text = "\n".join(cleaned).strip()
    return text
