# src/evaluator.py
"""
评测调度层
负责加载规则、预处理文本、调用各 metrics 并汇总评分结果。
"""

import dataclasses
from typing import Dict, Any, List, Optional, Mapping
from pathlib import Path
from src.utils import split_into_lines
from src.metrics.pingze import check_line
from src.metrics.rhyme import check_rhyme, load_yunbu_table
from src.metrics.antithesis import check_antithesis
from src.metrics.semantic import check_semantic
from src.schema.rule_config import RuleConfig


def _object_to_dict(obj) -> Optional[Dict[str, Any]]:
    """将规则配置对象安全转为字典，不成功则返回 None"""
    if obj is None:
        return None
    # Pydantic v2
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()
    # Pydantic v1
    if hasattr(obj, 'dict'):
        return obj.dict()
    # dataclass（仅实例，非类本身）
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    # 普通对象：取 __dict__ 并转为普通 dict
    if hasattr(obj, '__dict__'):
        return dict(vars(obj))
    return None

class Evaluator:
    def __init__(self, rule_config: RuleConfig):
        """
        初始化评测器
        :param rule_config: 已加载的词牌规则对象（RuleConfig）
        """
        self.rule = rule_config
        # 展平所有 stanza 的句子规则
        self.rule_lines = []
        for stanza in rule_config.stanzas:
            self.rule_lines.extend(stanza.lines)
        # 加载韵部表（只加载一次）
        self.yunbu_table = load_yunbu_table()

    def evaluate(self, ci_text: str, prompt_context: str = "") -> Dict[str, Any]:
        """
        评测一首完整的词
        :param ci_text: 词作原始文本（可含标点）
        :param prompt_context: 生成时的prompt（用于语义一致性检查）
        :return: 结构化评分结果
        """
        # 1. 预处理
        lines = split_into_lines(ci_text)

        # 2. 基础结构检查
        expected_count = len(self.rule_lines)
        actual_count = len(lines)
        structure_ok = (actual_count == expected_count)

        # 3. 逐句平仄检查
        pingze_results = []
        for i, (line, rl) in enumerate(zip(lines, self.rule_lines)):
            tpl = rl.text_tpl
            strict = rl.strict_positions
            res = check_line(line, tpl, strict)
            res["sentence_index"] = i + 1
            res["line_text"] = line
            pingze_results.append(res)

        # 4. 押韵检查
        rhyme_chars = []
        for i, (line, rl) in enumerate(zip(lines, self.rule_lines)):
            if rl.rhyme:  # 该句需押韵
                rhyme_chars.append(line[-1])  # 取尾字
        rhyme_result = check_rhyme(rhyme_chars, self.yunbu_table)

        # 5. 对仗检查
        antithesis_results = []
        # 提取对仗配置（兼容对象属性和纯字典）
        antithesis_config = None
        if hasattr(self.rule, 'special_rules') and self.rule.special_rules:
            sr = self.rule.special_rules
            if hasattr(sr, 'antithesis'):
                antithesis_config = _object_to_dict(sr.antithesis)

        # 从配置中获取必对/宜对列表，若没有则使用默认
        required_pairs = []
        recommended_pairs = []
        if isinstance(antithesis_config, dict):
            required_pairs = antithesis_config.get('required', [])
            recommended_pairs = antithesis_config.get('recommended', [])

        # 兜底：无配置时用鹧鸪天默认对仗位置
        if not required_pairs and not recommended_pairs:
            if len(lines) >= 4:
                required_pairs = [[3, 4]]
            if len(lines) >= 6:
                recommended_pairs = [[5, 6]]

        # 处理必对仗
        for pair in required_pairs:
            if isinstance(pair, list) and len(pair) == 2:
                idx_a, idx_b = pair[0] - 1, pair[1] - 1
                if idx_a < len(lines) and idx_b < len(lines):
                    res = check_antithesis(lines[idx_a], lines[idx_b], antithesis_config)
                    res["sentence_pair"] = [idx_a + 1, idx_b + 1]
                    antithesis_results.append(res)

        # 处理宜对偶
        for pair in recommended_pairs:
            if isinstance(pair, list) and len(pair) == 2:
                idx_a, idx_b = pair[0] - 1, pair[1] - 1
                if idx_a < len(lines) and idx_b < len(lines):
                    res = check_antithesis(lines[idx_a], lines[idx_b], antithesis_config)
                    res["sentence_pair"] = [idx_a + 1, idx_b + 1]
                    res["type"] = "recommended"
                    antithesis_results.append(res)

        # 6. 语义检查
        semantic_result = check_semantic(ci_text, prompt_context)

        # 7. 汇总
        overall = self._compute_overall(
            structure_ok,
            pingze_results,
            rhyme_result,
            antithesis_results,
            semantic_result
        )

        return {
            "structure_ok": structure_ok,
            "expected_lines": expected_count,
            "actual_lines": actual_count,
            "pingze": pingze_results,
            "rhyme": rhyme_result,
            "antithesis": antithesis_results,
            "semantic": semantic_result,
            "overall": overall
        }

    def _compute_overall(
        self,
        structure_ok: bool,
        pingze_results: List[Dict],
        rhyme_result: Dict,
        antithesis_results: List[Dict],
        semantic_result: Dict
    ) -> Dict[str, Any]:
        """计算总分及各项得分（100分制）"""
        scores = {}

        # 结构（10分）
        scores["structure"] = 10.0 if structure_ok else 0.0

        # 平仄（30分）：所有句子的平均匹配率 × 30
        if pingze_results:
            avg_pingze = sum(r["pingze_match_ratio"] for r in pingze_results) / len(pingze_results)
            scores["pingze"] = round(avg_pingze * 30, 2)
        else:
            scores["pingze"] = 0.0

        # 押韵（20分）：完全押韵得20，否则按一致性比例
        if rhyme_result["rhyme_ok"]:
            scores["rhyme"] = 20.0
        else:
            first_yunbu = rhyme_result["char_yunbu"][0] if rhyme_result["char_yunbu"] else None
            if first_yunbu and first_yunbu != "未知":
                same_count = sum(1 for y in rhyme_result["char_yunbu"] if y == first_yunbu)
                scores["rhyme"] = round(20.0 * (same_count / len(rhyme_result["char_yunbu"])), 2)
            else:
                scores["rhyme"] = 0.0

        # 对仗（20分）：取所有对仗检查的平均分 × 20
        if antithesis_results:
            avg_anti = sum(r["score"] for r in antithesis_results) / len(antithesis_results)
            scores["antithesis"] = round(avg_anti * 20, 2)
        else:
            scores["antithesis"] = 20.0  # 无检查项时默认满分

        # 语义（20分）
        scores["semantic"] = round(semantic_result["score"] * 20, 2)

        # 总分
        total = sum(scores.values())
        return {
            "total": round(total, 2),
            "breakdown": scores,
            "max_total": 100
        }