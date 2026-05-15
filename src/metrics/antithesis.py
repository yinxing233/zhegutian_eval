# src/metrics/antithesis.py
"""
对仗检查模块（LLM-based，缺陷检测模式）
"""

from typing import Any, Dict, Mapping, Optional

from src.llm_client import LLMClient

ANTITHESIS_PROMPT = """你是一位严格的诗词格律质检员，专门挑出对仗的缺陷。
请分析以下两句词的对仗质量。对仗必须满足：
1. 词性精确对应（名词对名词、动词对动词、形容词对形容词、数量词对数量词等）。
2. 语法结构一致（偏正结构对偏正结构、主谓对主谓等）。
3. 两句意思互相呼应或形成工整对比，不能毫无关联。

上句：{line_a}
下句：{line_b}

请以JSON格式输出，包含：
- score: 0到1之间的分数，1.0表示完全工整，0表示完全不对仗。
- reason: 简短理由，需明确指出缺陷（如有）。

示例输出：
{{"score": 0.3, "reason": "词性不对：‘红’(形)对‘翁’(名)；结构不同：上句主谓，下句动宾。"}}
"""


def check_antithesis(
    line_a: str, line_b: str, rule_antithesis: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    client = LLMClient()
    prompt = ANTITHESIS_PROMPT.format(line_a=line_a, line_b=line_b)
    result = client.ask_json(prompt)

    if "error" in result:
        return {
            "enabled": True,
            "score": 0.0,  # 失败时不给满分，避免污染
            "detail": f"LLM评估失败: {result.get('error', 'unknown')}",
        }

    return {
        "enabled": True,
        "score": float(result.get("score", 0.0)),
        "detail": result.get("reason", ""),
    }
