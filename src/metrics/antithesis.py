# src/metrics/antithesis.py
"""
对仗检查模块（LLM-based，当前为占位实现）
"""

from typing import Dict, Any, Mapping, Optional


def check_antithesis(
    line_a: str,
    line_b: str,
    rule_antithesis: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """
    检查两句是否对仗。

    当前为占位实现，返回未启用状态。
    未来接入 LLM 进行词性、结构、意境对齐评分。

    参数：
        line_a: 第一句（如词作第3句）
        line_b: 第二句（如词作第4句）
        rule_antithesis: 规则中 special_rules.antithesis 的内容（可选）

    返回：
        {
            "enabled": false,
            "score": 1.0,          # 归一化得分 (0~1)
            "detail": str          # 说明
        }
    """
    return {
        "enabled": False,
        "score": 1.0,  # 默认满分，避免影响总分（视为未启用时不扣分）
        "detail": "对仗检查未启用（需接入LLM）"
    }