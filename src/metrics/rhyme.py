"""
押韵检查模块
基于可版本化音韵 profile，检查韵脚是否同韵。
MVP 默认 profile 为中华新韵十四韵（xinyun_14）。
"""

from collections import Counter
from typing import Any, Dict, List

from src.prosody import load_prosody_profile
from utils.text_utils import get_final


def load_yunbu_table(path: str = None) -> Dict[str, str]:
    """加载 MVP 默认的中华新韵十四韵表。

    ``path`` 参数仅为旧调用兼容保留；音韵数据现在由 profile 统一管理。
    """
    if path is not None:
        raise ValueError("自定义韵表路径已停用，请使用 ProsodyProfile")
    return load_prosody_profile("xinyun_14").rhyme_groups


def get_yunbu(char: str, yunbu_table: Dict[str, str]) -> str:
    """返回单个汉字所属韵部名，无法识别返回 '未知'"""
    return yunbu_table.get(get_final(char), "未知")


def check_rhyme(
    rhyme_chars: List[str],
    yunbu_table: Dict[str, str] = None,
    expected_count: int = None,
) -> Dict[str, Any]:
    """
    检查一组韵脚字是否押韵（同属一个韵部）。

    参数：
        rhyme_chars: 需要押韵的句尾字列表（按顺序）
        yunbu_table: 韵部映射表，不传则自动加载

    返回：
        {
            "rhyme_ok": bool,               # 所有韵脚同韵
            "yunbu_name": str,              # 实际韵部（如果完全一致）
            "char_yunbu": [str, ...],       # 每个字的韵部
            "detail": str                   # 可读描述
        }
    """
    if yunbu_table is None:
        yunbu_table = load_yunbu_table()

    char_yunbu = [get_yunbu(c, yunbu_table) for c in rhyme_chars]
    expected_count = expected_count if expected_count is not None else len(rhyme_chars)
    known = [y for y in char_yunbu if y != "未知"]
    if not known:
        return {
            "rhyme_ok": False,
            "yunbu_name": "无",
            "char_yunbu": char_yunbu,
            "expected_count": expected_count,
            "known_count": 0,
            "dominant_yunbu": None,
            "dominant_count": 0,
            "unknown_chars": list(rhyme_chars),
            "detail": "无法识别任何韵脚字",
        }

    counts = Counter(known)
    dominant_yunbu, dominant_count = counts.most_common(1)[0]
    complete = len(rhyme_chars) == expected_count and len(known) == expected_count
    all_same = complete and dominant_count == expected_count

    return {
        "rhyme_ok": all_same,
        "yunbu_name": dominant_yunbu if all_same else "混押或缺失",
        "char_yunbu": char_yunbu,
        "expected_count": expected_count,
        "known_count": len(known),
        "dominant_yunbu": dominant_yunbu,
        "dominant_count": dominant_count,
        "unknown_chars": [
            c for c, group in zip(rhyme_chars, char_yunbu) if group == "未知"
        ],
        "detail": "全押同一韵部" if all_same else f"韵部不一致: {char_yunbu}",
    }
