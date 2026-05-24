"""
押韵检查模块
基于中华新韵十八韵，检查韵脚是否同韵
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from utils.text_utils import get_pinyin


def load_yunbu_table(path: str = None) -> Dict[str, str]:
    """加载韵部映射表（韵母 -> 韵部名）"""
    if path is None:
        path = Path(__file__).parent.parent.parent / "data" / "zhonghua_xinyun.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["yunbu"]


def get_yunbu(char: str, yunbu_table: Dict[str, str]) -> str:
    """返回单个汉字所属韵部名，无法识别返回 '未知'"""
    py = get_pinyin(char)
    # 提取韵母：去掉声母，保留剩余部分
    # 简单方法：从拼音中提取最后一个元音开始的子串
    # 由于映射表 key 有限，我们尝试直接匹配后缀
    for suffix in sorted(yunbu_table.keys(), key=lambda x: -len(x)):
        if py.endswith(suffix):
            return yunbu_table[suffix]
    return "未知"


def check_rhyme(
    rhyme_chars: List[str], yunbu_table: Dict[str, str] = None
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
    # 过滤掉“未知”
    known = [y for y in char_yunbu if y != "未知"]
    if not known:
        return {
            "rhyme_ok": False,
            "yunbu_name": "无",
            "char_yunbu": char_yunbu,
            "detail": "无法识别任何韵脚字",
        }

    first_yunbu = known[0]
    all_same = all(y == first_yunbu for y in known)

    return {
        "rhyme_ok": all_same,
        "yunbu_name": first_yunbu if all_same else "混押",
        "char_yunbu": char_yunbu,
        "detail": "全押同一韵部" if all_same else f"韵部不一致: {char_yunbu}",
    }
