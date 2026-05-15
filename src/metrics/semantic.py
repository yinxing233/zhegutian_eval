# src/metrics/semantic.py
"""
语义/意境检查模块（LLM-based，缺陷检测模式）
"""

from typing import Any, Dict

from src.llm_client import LLMClient

SEMANTIC_PROMPT = """你是一位专挑诗词毛病的质检员，请严格评估这首词的语义质量。
评估要点（扣分制，满分1.0）：
1. 主题一致性：全词是否围绕同一主题？有无断裂、跳跃？
2. 意象具体性：是否使用不可替换的具体细节，而非泛泛的“愁”“梦”“泪”？发现空洞堆砌立即扣分。
3. 情感推进：情绪是否有层次，还是平铺直叙？
4. 语言流畅度：句子衔接是否自然，有无生硬拼凑？

词作全文：
{ci_text}

上下文/创作要求：{prompt_context}

请以JSON格式输出：
- score: 0~1的分数，1.0为完美，0为完全不合格。
- reason: 简短理由，重点说明扣分原因。
"""


def check_semantic(ci_text: str, prompt_context: str = "") -> Dict[str, Any]:
    client = LLMClient()
    prompt = SEMANTIC_PROMPT.format(ci_text=ci_text, prompt_context=prompt_context)
    result = client.ask_json(prompt)

    if "error" in result:
        return {
            "enabled": True,
            "score": 0.0,
            "detail": f"LLM评估失败: {result.get('error', 'unknown')}",
        }

    return {
        "enabled": True,
        "score": float(result.get("score", 0.0)),
        "detail": result.get("reason", ""),
    }
