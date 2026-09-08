import unittest
from unittest.mock import patch

from src.metrics.antithesis import check_antithesis
from src.metrics.semantic import check_semantic


class LlmMetricContractTests(unittest.TestCase):
    @patch("src.metrics.semantic.LLMClient")
    def test_semantic_rejects_out_of_range_score(self, client_factory):
        client_factory.return_value.ask_json.return_value = {
            "score": 1.5,
            "reason": "bad",
            "raw": "{}",
        }
        result = check_semantic("测试")
        self.assertFalse(result["success"])
        self.assertIsNone(result["score"])
        self.assertEqual(result["error_type"], "score_out_of_range")

    @patch("src.metrics.antithesis.LLMClient")
    def test_antithesis_client_init_failure_is_missing(self, client_factory):
        client_factory.side_effect = ValueError("missing key")
        result = check_antithesis("上句", "下句")
        self.assertFalse(result["success"])
        self.assertIsNone(result["score"])
        self.assertEqual(result["error_type"], "client_init_failed")


if __name__ == "__main__":
    unittest.main()
