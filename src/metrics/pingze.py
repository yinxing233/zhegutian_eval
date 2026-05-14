"""
平仄检查模块
基于单句规则模板，计算平仄匹配度
"""

from typing import List, Dict, Any
from src.utils import is_ping, is_ze


def check_line(
    line: str,
    text_tpl: str,
    strict_positions: List[int]
) -> Dict[str, Any]:
    """
    检查单句平仄是否符合规则模板。

    参数：
        line: 清洗后的汉字句子（如 "彩袖殷勤捧玉钟"）
        text_tpl: 平仄模板，由 平/仄/中 组成（如 "中仄平平中仄平"）
        strict_positions: 严格检查位置列表（1-based，如 [2,4,6,7]）

    返回：
        {
            "char_count_ok": bool,          # 字数正确
            "pingze_match_ratio": float,    # 总匹配率（跳过"中"）
            "strict_match_ratio": float,    # 严格位置匹配率
            "error_positions": [int, ...]   # 出错的字位置（1-based）
        }
    """
    if len(line) != len(text_tpl):
        return {
            "char_count_ok": False,
            "pingze_match_ratio": 0.0,
            "strict_match_ratio": 0.0,
            "error_positions": []
        }

    total_checked = 0
    total_matched = 0
    strict_checked = 0
    strict_matched = 0
    errors = []

    for i, (char, tpl) in enumerate(zip(line, text_tpl)):
        pos = i + 1  # 1-based
        if tpl == "中":
            continue  # 不检查

        total_checked += 1
        expected_ping = (tpl == "平")
        actual_ping = is_ping(char)

        if expected_ping == actual_ping:
            total_matched += 1
        else:
            errors.append(pos)

        if pos in strict_positions:
            strict_checked += 1
            if expected_ping == actual_ping:
                strict_matched += 1

    match_ratio = total_matched / total_checked if total_checked > 0 else 1.0
    strict_ratio = strict_matched / strict_checked if strict_checked > 0 else 1.0

    return {
        "char_count_ok": True,
        "pingze_match_ratio": round(match_ratio, 4),
        "strict_match_ratio": round(strict_ratio, 4),
        "error_positions": errors
    }