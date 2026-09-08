import json
import tempfile
import unittest
from pathlib import Path

from tools.compare_eval import load_results, version_path
from tools.delta_snapshot import resolve_eval_dir


class ToolCompatibilityTests(unittest.TestCase):
    def test_versioned_evaluator_paths_are_discovered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_001"
            eval_dir = run_dir / "evaluations" / "eval_v0.3.0"
            eval_dir.mkdir(parents=True)
            result_path = eval_dir / "eval_results.jsonl"
            result_path.write_text(
                json.dumps({"task_id": "a", "normalized_score": 80}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(resolve_eval_dir(run_dir), eval_dir)
            self.assertEqual(version_path(run_dir, "v0.3.0"), result_path)
            self.assertIn("a", load_results(result_path))

    def test_legacy_evaluator_path_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_001"
            run_dir.mkdir()
            result_path = run_dir / "eval_results.jsonl"
            result_path.write_text(
                json.dumps({"task_id": "a", "eval_version": "v0.2.2"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(resolve_eval_dir(run_dir), run_dir)
            self.assertEqual(version_path(run_dir, "v0.2.2"), result_path)


if __name__ == "__main__":
    unittest.main()
