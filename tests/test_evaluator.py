import unittest
from unittest.mock import patch

from src.evaluator import Evaluator
from src.schema.rule_config import load_rule_config


CI_TEXT = (
    "彩袖殷勤捧玉钟，且拼红烛为君容。"
    "舞低杨柳楼心月，歌尽桃花扇底风。"
    "从别后，忆相逢，几回魂梦与君同。"
    "今宵剩把银釭照，犹恐相逢是梦中。"
)


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = Evaluator(
            load_rule_config("rules/zhegutian_zhengti.json")
        )

    def test_offline_conditional_result_has_explicit_missingness(self):
        result = self.evaluator.evaluate_conditional(CI_TEXT, enable_llm=False)
        self.assertEqual(result["actual_lines"], 9)
        self.assertEqual(result["overall"]["coverage"], 0.6)
        self.assertEqual(result["dimension_status"]["semantic"], "rule_skip")
        self.assertEqual(result["prosody_profile"], "xinyun_14")

    def test_required_words_are_checked_even_when_semantic_is_skipped(self):
        result = self.evaluator.evaluate_conditional(
            CI_TEXT,
            constraints={
                "rhyme_system": "中华新韵",
                "required_words": ["剑", "霜"],
            },
            enable_llm=False,
        )
        self.assertEqual(
            result["constraint_violations"],
            [{"type": "missing_required_words", "words": ["剑", "霜"]}],
        )

    def test_unknown_target_rhyme_group_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不存在韵部"):
            self.evaluator.evaluate_conditional(
                CI_TEXT,
                constraints={
                    "prosody_profile": "xinyun_14",
                    "rhyme_bu": "不存在的韵部",
                },
                enable_llm=False,
            )

    @patch("src.evaluator.check_semantic")
    @patch("src.evaluator.check_antithesis")
    def test_full_evaluation_uses_weighted_antithesis(
        self, antithesis_mock, semantic_mock
    ):
        antithesis_mock.side_effect = [
            {"success": True, "score": 1.0, "detail": "", "raw": ""},
            {"success": True, "score": 0.0, "detail": "", "raw": ""},
        ]
        semantic_mock.return_value = {
            "success": True,
            "score": 0.8,
            "reason": "",
            "raw": "",
        }
        result = self.evaluator.evaluate(CI_TEXT)
        self.assertEqual(result["overall"]["coverage"], 1.0)
        self.assertEqual(result["overall"]["breakdown"]["antithesis"], 13.33)
        self.assertEqual(result["overall"]["breakdown"]["semantic"], 16.0)

    @patch("src.evaluator.check_semantic")
    @patch("src.evaluator.check_antithesis")
    def test_judge_failure_is_missing_not_zero(
        self, antithesis_mock, semantic_mock
    ):
        antithesis_mock.return_value = {
            "success": False,
            "score": None,
            "error_type": "test_failure",
            "detail": "",
            "raw": "",
        }
        semantic_mock.return_value = {
            "success": False,
            "score": None,
            "error_type": "test_failure",
            "raw": "",
        }
        result = self.evaluator.evaluate(CI_TEXT)
        self.assertNotIn("antithesis", result["overall"]["breakdown"])
        self.assertNotIn("semantic", result["overall"]["breakdown"])
        self.assertEqual(result["overall"]["coverage"], 0.6)
        self.assertEqual(result["dimension_status"]["antithesis"], "judge_fail")
        self.assertEqual(result["dimension_status"]["semantic"], "judge_fail")

    def test_no_failure_does_not_create_unknown_instability(self):
        tags = self.evaluator.infer_instability_pattern(
            {
                "structure": 10,
                "pingze": 30,
                "rhyme": 20,
                "antithesis": 20,
                "semantic": 20,
            },
            generated=CI_TEXT,
            finish_reason="stop",
        )
        self.assertEqual(tags, [])

    def test_proxy_diagnosis_keeps_one_primary_field(self):
        tags = self.evaluator.infer_instability_pattern(
            {
                "structure": 10,
                "pingze": 28,
                "rhyme": 20,
                "antithesis": 15,
                "semantic": 6,
            },
            generated=CI_TEXT,
            finish_reason="stop",
        )
        self.assertEqual(
            tags,
            [{"symptom": "template_parroting", "primary_field": "F_imagery"}],
        )

    def test_missing_semantic_keeps_m_layer_without_f_inference(self):
        tags = self.evaluator.infer_instability_pattern(
            {
                "structure": 0,
                "pingze": 10,
                "rhyme": 5,
                "antithesis": None,
                "semantic": None,
            },
            generated="残句",
            finish_reason="stop",
        )
        self.assertEqual(
            [tag["symptom"] for tag in tags],
            ["structure_incomplete", "tone_fail", "rhyme_fail"],
        )

    def test_finish_reason_is_normalized(self):
        for value in ("length", "MAX_TOKENS", "FinishReason.MAX_TOKENS"):
            self.assertEqual(self.evaluator.normalize_finish_reason(value), "length")


if __name__ == "__main__":
    unittest.main()
