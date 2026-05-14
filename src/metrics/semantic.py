# src/metrics/semantic.py
"""
语义/意境检查模块（LLM-based，当前为占位实现）
"""

from typing import Dict, Any


def check_semantic(ci_text: str, prompt_context: str = "") -> Dict[str, Any]:
    """
    检查整首词的语义一致性、意境与主题契合度。

    当前为占位实现，返回未启用状态。
    未来接入 LLM 进行主题漂移、意象模板化等评估。

    参数：
        ci_text: 完整词作文本
        prompt_context: 生成所用的prompt（若有），用于主题一致性判断

    返回：
        {
            "enabled": false,
            "score": 1.0,          # 归一化得分 (0~1)
            "detail": str
        }
    """
    return {
        "enabled": False,
        "score": 1.0,  # 默认满分，视为未启用时不扣分
        "detail": "语义检查未启用（需接入LLM）"
    }