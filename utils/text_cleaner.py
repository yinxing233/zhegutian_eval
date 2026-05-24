"""
统一文本清洗工具
clean_text: 通用卫生层（所有 provider 通用）
"""

import unicodedata


def clean_text(text: str) -> str:
    """
    通用卫生层：只做所有 provider 都安全的操作。
    - NFKC 归一化
    - 移除末尾 [END]
    - 首尾空白清理
    不做空行压缩、不做正文提取、不删任何内容。
    """
    if text is None:
        return ""

    text = text.strip()
    if not text:
        return ""

    # Unicode NFKC 归一化（token manifold normalization）
    text = unicodedata.normalize("NFKC", text)

    # 删除末尾的 [END]
    if text.rstrip().endswith("[END]"):
        text = text.rstrip()[:-5].strip()

    return text
