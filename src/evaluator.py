"""
评测调度层
负责加载规则、预处理文本、调用各 metrics 并汇总评分结果。
"""

import dataclasses
from typing import Any, Dict, List, Optional

from src.metrics.antithesis import check_antithesis
from src.metrics.pingze import check_line
from src.metrics.rhyme import check_rhyme, get_yunbu, load_yunbu_table
from src.metrics.semantic import check_semantic
from src.schema.rule_config import RuleConfig
from utils.text_utils import split_into_lines


def _object_to_dict(obj) -> Optional[Dict[str, Any]]:
    """将规则配置对象安全转为字典，不成功则返回 None"""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return None


class Evaluator:
    def __init__(self, rule_config: RuleConfig):
        self.rule = rule_config
        self.rule_lines = []
        for stanza in rule_config.stanzas:
            self.rule_lines.extend(stanza.lines)
        self.yunbu_table = load_yunbu_table()

    def evaluate(
        self,
        ci_text: str,
        prompt_context: str = "",
        skip_semantic: bool = False,
        skip_antithesis: bool = False,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        评测一首完整的词
        :param ci_text: 词作原始文本
        :param prompt_context: 生成时的 prompt（用于语义一致性检查）
        :param skip_semantic: 是否跳过 LLM 语义评测
        :param constraints: 任务约束字典，包含 rhyme_bu（限定韵部）、required_words（必含词）等
        :return: 结构化评分结果
        """
        # 1. 预处理
        lines = split_into_lines(ci_text)

        # 2. 基础结构检查
        expected_count = len(self.rule_lines)
        actual_count = len(lines)
        structure_ok = actual_count == expected_count

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
            if rl.rhyme:
                rhyme_chars.append(line[-1] if line else "")
        rhyme_result = check_rhyme(rhyme_chars, self.yunbu_table)

        # 5. 对仗检查（LLM-based，可跳过以节省评测配额）
        antithesis_results = []
        if not skip_antithesis:
            for item in self._collect_antithesis_pairs(lines):
                idx_a, idx_b, rule_detail = item
                res = check_antithesis(lines[idx_a], lines[idx_b], rule_detail)
                res["sentence_pair"] = [idx_a + 1, idx_b + 1]
                antithesis_results.append(res)

        # 6. 语义检查（可根据开关跳过）
        if skip_semantic:
            semantic_result = {
                "success": False,
                "score": None,
                "error_type": "skip_semantic",
                "reason": "语义评测已跳过（skip_semantic=True）",
            }
        else:
            semantic_result = check_semantic(ci_text, prompt_context)

        # 7. 汇总基础得分
        # 跳过对仗评测时，传入 None 表示该维度未评测（不计入总分）
        overall = self._compute_overall(
            structure_ok,
            pingze_results,
            rhyme_result,
            antithesis_results if not skip_antithesis else None,
            semantic_result,
        )
        scores = overall["breakdown"]

        # 8. 应用任务约束扣分（如果提供了 constraints）
        if constraints:
            # 8.1 限定韵部检查
            rhyme_bu = constraints.get("rhyme_bu")
            if rhyme_bu and rhyme_chars:
                violation_count = 0
                for char in rhyme_chars:
                    if char and get_yunbu(char, self.yunbu_table) != rhyme_bu:
                        violation_count += 1
                # 每个违规韵脚扣 3 分，上限扣完韵部分
                scores["rhyme"] = max(0.0, scores["rhyme"] - violation_count * 3)

            # 8.2 必含词检查（仅在语义已评测时扣分；跳过/未评测时记录缺失原因）
            required_words = constraints.get("required_words", [])
            if required_words:
                missing = [w for w in required_words if w not in ci_text]
                if missing:
                    if "semantic" in scores:
                        scores["semantic"] = max(0.0, scores["semantic"] - len(missing) * 5)
                    else:
                        semantic_missing_reason = (
                            f"missing_required_words:{','.join(missing)}"
                        )

            # 重新计算总分
            overall["total"] = round(sum(scores.values()), 2)
            overall["breakdown"] = scores

        # 判断语义是否真正被评测（非跳过、非裁判失败）
        semantic_evaluated = False
        semantic_missing_reason = None
        if skip_semantic:
            semantic_evaluated = False
            semantic_missing_reason = "skip_semantic"
        elif not semantic_result.get("success", True):
            semantic_evaluated = False
            semantic_missing_reason = (
                f"judge_fail:{semantic_result.get('error_type', 'unknown')}"
            )
        else:
            semantic_evaluated = True

        # 9. 收集 failure_trace (时序崩塌追踪)
        failure_trace = []

        # 9.1 结构不完整
        if not structure_ok:
            failure_trace.append(
                {
                    "step": len(failure_trace) + 1,
                    "type": "structure_incomplete",
                    "detail": f"期望句数 {expected_count}，实际句数 {actual_count}",
                }
            )

        # 9.2 逐句平仄错误
        for r in pingze_results:
            if r.get("error_positions"):
                failure_trace.append(
                    {
                        "step": len(failure_trace) + 1,
                        "line": r["sentence_index"],
                        "type": "pingze_fail",
                        "detail": f"第 {r['sentence_index']} 句平仄不符，出错位置：{r['error_positions']}",
                    }
                )

        # 9.3 押韵错误
        if not rhyme_result.get("rhyme_ok"):
            failure_trace.append(
                {
                    "step": len(failure_trace) + 1,
                    "type": "rhyme_fail",
                    "detail": rhyme_result.get("detail", "押韵失败"),
                }
            )

        # 9.4 对仗错误
        for r in antithesis_results:
            if r.get("score", 1.0) < 0.8:  # 设定对仗不工整阈值
                pair = r.get("sentence_pair", [])
                failure_trace.append(
                    {
                        "step": len(failure_trace) + 1,
                        "lines": pair,
                        "type": "antithesis_fail",
                        "detail": f"第 {pair} 句对仗不工整，得分：{r.get('score')}, 详情：{r.get('detail')}",
                    }
                )

        return {
            "structure_ok": structure_ok,
            "expected_lines": expected_count,
            "actual_lines": actual_count,
            "pingze": pingze_results,
            "rhyme": rhyme_result,
            "antithesis": antithesis_results,
            "semantic": semantic_result,
            "semantic_evaluated": semantic_evaluated,
            "semantic_missing_reason": semantic_missing_reason,
            "overall": overall,
            "failure_trace": failure_trace,
        }

    @staticmethod
    def infer_instability_pattern(
        metrics: Dict[str, float],
        generated: str = "",
        finish_reason: str = "",
        reasoning_content: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        根据各维度得分和生成状态，推断失稳模式标签。
        返回冻结版 taxonomy：每个元素为 {"symptom": str, "primary_field": str}
        primary_field 取值：M_ONLY, F_imagery, F_emotional, NONE（永不缺失）
        """
        tags: List[Dict[str, str]] = []

        # ---------- 1. 纯 M 层症状（primary_field = "M_ONLY"） ----------

        # reasoning_overflow：推理链过长
        if finish_reason in ("length", "MAX_TOKENS") and reasoning_content:
            gen_len = len(generated) if generated else 0
            if len(reasoning_content) > max(100, gen_len * 2):
                tags.append(
                    {"symptom": "reasoning_overflow", "primary_field": "M_ONLY"}
                )

        # empty_output：完全空输出（优先级最高，直接返回）
        if not generated or len(generated.strip()) == 0:
            tags.append({"symptom": "empty_output", "primary_field": "M_ONLY"})
            return tags

        # truncated：输出被截断
        if finish_reason == "length" and len(generated) < 40:
            tags.append({"symptom": "truncated", "primary_field": "M_ONLY"})

        # structure_incomplete：句数不对
        if metrics.get("structure", 10) < 8:
            tags.append({"symptom": "structure_incomplete", "primary_field": "M_ONLY"})

        # tone_fail：平仄大面积崩塌
        if metrics.get("pingze", 30) < 20:
            tags.append({"symptom": "tone_fail", "primary_field": "M_ONLY"})

        # rhyme_fail：押韵大面积崩塌
        if metrics.get("rhyme", 20) < 15:
            tags.append({"symptom": "rhyme_fail", "primary_field": "M_ONLY"})

        # ---------- 2. 深层诊断（需要 semantic 分数） ----------
        semantic = metrics.get("semantic")
        if semantic is None:
            if not tags:
                tags.append({"symptom": "unknown_instability", "primary_field": "NONE"})
            return tags

        pingze = metrics.get("pingze") or 0
        rhyme = metrics.get("rhyme") or 0
        antithesis = metrics.get("antithesis") or 0

        # template_parroting：格律稳定但语义空洞 → F_imagery
        if pingze >= 25 and rhyme >= 18 and semantic <= 8:
            tags.append({"symptom": "template_parroting", "primary_field": "F_imagery"})

        # aesthetic_entropy：平仄正常但语义极低 → F_emotional
        if pingze >= 25 and semantic <= 8:
            tags.append(
                {"symptom": "aesthetic_entropy", "primary_field": "F_emotional"}
            )

        # safe_mediocrity：语义中等但没有亮点 → NONE（无法归主导场）
        if 10 <= semantic <= 14:
            tags.append({"symptom": "safe_mediocrity", "primary_field": "NONE"})

        # ---------- 3. fragmentation 代理规则 ----------
        # 当 semantic 极低 + 平仄崩塌 + 非空输出 + 至少 2 句时，视为 catastrophic coherence failure proxy
        if (
            semantic is not None
            and semantic <= 5
            and pingze < 20
            and len(generated.strip()) > 0
            and generated.count("\n") >= 1  # 至少 2 句（一句 + 至少一个换行）
        ):
            tags.append({"symptom": "fragmentation", "primary_field": "NONE"})

        # ---------- 4. 兜底 ----------
        if not tags:
            tags.append({"symptom": "unknown_instability", "primary_field": "NONE"})

        return tags

    def _compute_overall(
        self,
        structure_ok: bool,
        pingze_results: List[Dict],
        rhyme_result: Dict,
        antithesis_results: Optional[List[Dict]],
        semantic_result: Dict,
    ) -> Dict[str, Any]:
        """计算总分及各项得分（100分制）。

        未评测维度（antithesis_results is None 或 semantic score is None）不计入
        breakdown 与总分，交由上层据覆盖率处理，遵循「缺失 ≠ 低质量」原则。
        """
        scores = {}

        # 结构（10分）
        scores["structure"] = 10.0 if structure_ok else 0.0

        # 平仄（30分）
        if pingze_results:
            avg_pingze = sum(r["pingze_match_ratio"] for r in pingze_results) / len(
                pingze_results
            )
            scores["pingze"] = round(avg_pingze * 30, 2)
        else:
            scores["pingze"] = 0.0

        # 押韵（20分）
        if rhyme_result["rhyme_ok"]:
            scores["rhyme"] = 20.0
        else:
            first_yunbu = (
                rhyme_result["char_yunbu"][0] if rhyme_result["char_yunbu"] else None
            )
            if first_yunbu and first_yunbu != "未知":
                same_count = sum(
                    1 for y in rhyme_result["char_yunbu"] if y == first_yunbu
                )
                scores["rhyme"] = round(
                    20.0 * (same_count / len(rhyme_result["char_yunbu"])), 2
                )
            else:
                scores["rhyme"] = 0.0

        # 对仗（20分）：仅在真正评测时计入
        if antithesis_results is not None:
            if antithesis_results:
                avg_anti = sum(r["score"] for r in antithesis_results) / len(
                    antithesis_results
                )
                scores["antithesis"] = round(avg_anti * 20, 2)
            else:
                # 结构破碎到无法成对：不给满分，记 0 分
                scores["antithesis"] = 0.0

        # 语义（20分）：None 表示未评测（跳过或裁判故障），不计入
        sem_score = semantic_result.get("score")
        if sem_score is not None:
            scores["semantic"] = round(sem_score * 20, 2)

        total = sum(scores.values())
        return {"total": round(total, 2), "breakdown": scores, "max_total": 100}

    def evaluate_semantic_only(
        self, ci_text: str, prompt_context: str = ""
    ) -> Dict[str, Any]:
        """
        单独进行语义评测（不重复计算格律）。
        用于 pipeline 在格律通过筛选后，按需补评语义。
        保持 evaluator 为唯一评测入口。
        """
        return check_semantic(ci_text, prompt_context)

    def _collect_antithesis_pairs(
        self, lines: List[str]
    ) -> List[tuple]:
        """收集需要对仗检查的句对。

        返回 [(idx_a, idx_b, rule_detail), ...]，下标为 0-based。
        rule_detail 为单条对仗规则字典（含 desc/type），供 LLM 裁判感知约束。
        规则未配置时按词牌默认位置兜底（上阕三四句必对、下阕三五句宜对）。
        """
        pairs: List[tuple] = []
        antithesis_config = None
        if hasattr(self.rule, "special_rules") and self.rule.special_rules:
            sr = self.rule.special_rules
            if hasattr(sr, "antithesis"):
                antithesis_config = _object_to_dict(sr.antithesis)

        required_items = []
        recommended_items = []
        if isinstance(antithesis_config, dict):
            required_items = antithesis_config.get("required", []) or []
            recommended_items = antithesis_config.get("recommended", []) or []

        # 兜底：规则未配置对仗时，按词牌默认位置推断
        if not required_items and not recommended_items:
            if len(lines) >= 4:
                required_items = [
                    {"pair": [3, 4], "desc": "", "type": "strict", "weight": 1.0}
                ]
            if len(lines) >= 6:
                recommended_items = [
                    {"pair": [5, 6], "desc": "", "type": "soft", "weight": 0.5}
                ]

        for item in required_items:
            pair = item.get("pair") if isinstance(item, dict) else item
            if isinstance(pair, list) and len(pair) == 2:
                idx_a, idx_b = pair[0] - 1, pair[1] - 1
                if idx_a < len(lines) and idx_b < len(lines):
                    pairs.append((idx_a, idx_b, item if isinstance(item, dict) else None))

        for item in recommended_items:
            pair = item.get("pair") if isinstance(item, dict) else item
            if isinstance(pair, list) and len(pair) == 2:
                idx_a, idx_b = pair[0] - 1, pair[1] - 1
                if idx_a < len(lines) and idx_b < len(lines):
                    pairs.append((idx_a, idx_b, item if isinstance(item, dict) else None))

        return pairs

    def evaluate_antithesis_only(self, ci_text: str) -> Optional[float]:
        """
        单独进行对仗评测（不重复计算格律）。
        用于 pipeline 在格律通过筛选后，按需补评对仗。
        返回 0~1 平均分；若结构过短无法成对或裁判故障，返回 None。
        """
        lines = split_into_lines(ci_text)
        pairs = self._collect_antithesis_pairs(lines)
        if not pairs:
            return None

        scores = []
        for idx_a, idx_b, rule_detail in pairs:
            res = check_antithesis(lines[idx_a], lines[idx_b], rule_detail)
            if not res.get("success", True):
                # 裁判故障：返回 None，交由上层记录 judge_fail
                return None
            scores.append(res.get("score", 0.0))

        if not scores:
            return None
        return sum(scores) / len(scores)
