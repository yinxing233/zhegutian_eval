# src/utils.py
"""
文本处理工具函数
- 文本清洗（去标点/空格）
- 断句（按标点）
- 拼音与声调提取（基于 pypinyin，现代汉语普通话）

音韵体系说明：
MVP 阶段使用中华新韵（现代汉语），基于 pypinyin 库。
平仄规则：一声/二声为平，三声/四声为仄，轻声归平。

未来切换至平水韵/词林正韵时需改动：
  1. 替换 is_ping/is_ze 函数（需引入入声字表）
  2. 替换 metrics/rhyme.py 中的韵部映射表
  3. 无其他文件受影响
"""

import re
from typing import List, Tuple
from pypinyin import pinyin, Style

# ---------------------------
# 常量定义
# ---------------------------

SENTENCE_DELIMITERS = re.compile(r'[，。！？、；：,.!?;:\s]+')
HAN_ONLY = re.compile(r'[^\u4e00-\u9fff]')

# ---------------------------
# 文本清洗与断句
# ---------------------------

def clean_text(text: str) -> str:
    """去除所有非汉字符号，返回纯汉字字符串"""
    return HAN_ONLY.sub('', text)


def split_into_lines(text: str) -> List[str]:
    """
    将词作文本按标点分割为句子列表。
    去除非汉字符号，过滤空字符串。
    
    注意：此函数不保证返回的句数与任何特定词牌匹配。
    对齐词牌结构是 evaluator 的职责。
    """
    raw_parts = re.split(SENTENCE_DELIMITERS, text.strip())
    parts = []
    for p in raw_parts:
        c = clean_text(p)
        if c:
            parts.append(c)
    return parts


# ---------------------------
# 拼音与声调（单字）
# ---------------------------

def get_pinyin_tone(char: str) -> Tuple[str, int]:
    """
    返回 (拼音不带声调, 声调数字)
    例如：'中' → ('zhong', 1)
    多音字采用 pypinyin 默认输出
    """
    if len(char) != 1:
        raise ValueError("只接受单个汉字")
    py = pinyin(char, style=Style.TONE3, heteronym=False)[0][0]
    match = re.match(r'^([a-zA-ZüÜ]+)(\d)$', py)
    if match:
        syllable = match.group(1)
        tone = int(match.group(2))
        return syllable, tone
    else:
        return py, 0


def get_pinyin(char: str) -> str:
    """仅返回不带声调的拼音"""
    return get_pinyin_tone(char)[0]


def get_tone(char: str) -> int:
    """仅返回声调数字（1/2/3/4/0）"""
    return get_pinyin_tone(char)[1]


def is_ping(char: str) -> bool:
    """判断是否为平声（现代：一声、二声、轻声为平）"""
    tone = get_tone(char)
    return tone in (1, 2, 0)


def is_ze(char: str) -> bool:
    """判断是否为仄声（三声、四声）"""
    tone = get_tone(char)
    return tone in (3, 4)


# ---------------------------
# 批量操作（整句）
# ---------------------------

def get_tones(line: str) -> List[int]:
    """返回一行中每个字的声调列表"""
    return [get_tone(c) for c in line]