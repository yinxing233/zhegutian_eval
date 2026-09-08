import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import batch_evaluate
import batch_generate
from batch_evaluate import atomic_write_jsonl, evaluate_record
from src.evaluator import Evaluator
from src.schema.rule_config import load_rule_config


class BatchEvaluateTests(unittest.TestCase):
    def test_generation_normalization_freezes_prosody_profile(self):
        sample = batch_generate.normalize_sample(
            {"task_id": "a", "L0_constraints": {"rhyme_system": "中华新韵"}}
        )
        self.assertEqual(sample["L0_constraints"]["prosody_profile"], "xinyun_14")

    def test_failed_serialization_keeps_previous_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.jsonl"
            path.write_text("old\n", encoding="utf-8")
            with self.assertRaises(TypeError):
                atomic_write_jsonl(path, [{"bad": object()}])
            self.assertEqual(path.read_text(encoding="utf-8"), "old\n")

    def test_snapshot_preserves_task_layers_and_constraint_result(self):
        evaluator = Evaluator(load_rule_config("rules/zhegutian_zhengti.json"))
        record = {
            "task_id": "test",
            "generated": "空山。",
            "finish_reason": "STOP",
            "L0_surface_prompt": "测试提示",
            "L0_constraints": {
                "rhyme_system": "中华新韵",
                "required_words": ["剑"],
            },
            "L1_expected_failure_modes": ["template_parroting"],
            "L2_latent_tensions": ["测试张力"],
        }
        snapshot, failures = evaluate_record(
            evaluator,
            record,
            index=0,
            run_dir=Path("runs/test"),
            judge_model="offline",
            judge_provider="offline",
            threshold_ratio=0.8,
            min_pingze=20,
            enable_llm=False,
        )
        self.assertEqual(snapshot["L0_surface_prompt"], "测试提示")
        self.assertEqual(snapshot["L2_latent_tensions"], ["测试张力"])
        self.assertIn("constraint_violation", snapshot["error_category"])
        self.assertEqual(failures, [])
        json.dumps(snapshot, ensure_ascii=False)

    def test_offline_main_is_versioned_and_idempotent(self):
        rule = load_rule_config("rules/zhegutian_zhengti.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "runs" / "run_001_test"
            run_dir.mkdir(parents=True)
            record = {
                "task_id": "offline",
                "generated": "空山。",
                "finish_reason": "STOP",
                "L0_surface_prompt": "测试",
                "L0_constraints": {"prosody_profile": "xinyun_14"},
            }
            (run_dir / "generated_results.jsonl").write_text(
                json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            args = SimpleNamespace(run="run_001_test", replay=True, offline=True)
            with (
                patch.object(batch_evaluate, "PROJECT_ROOT", root),
                patch.object(batch_evaluate, "parse_args", return_value=args),
                patch.object(batch_evaluate, "load_rule_config", return_value=rule),
                patch.object(batch_evaluate, "sha256_files", return_value="test-hash"),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(batch_evaluate.main(), 0)
                self.assertEqual(batch_evaluate.main(), 0)

            eval_dir = run_dir / "evaluations" / "eval_v0.3.0"
            results = (eval_dir / "eval_results.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(results), 1)
            metadata = json.loads(
                (eval_dir / "eval_metadata.json").read_text(encoding="utf-8")
            )
            self.assertTrue(metadata["offline"])
            self.assertEqual(metadata["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
