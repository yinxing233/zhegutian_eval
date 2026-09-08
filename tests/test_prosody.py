import json
import tempfile
import unittest
from pathlib import Path

from src.metrics.rhyme import check_rhyme
from src.prosody import load_prosody_profile
from src.schema.rule_config import load_rule_config
from utils.text_utils import get_final


class ProsodyTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_prosody_profile("xinyun_14")

    def test_xinyun_14_eleventh_geng(self):
        for char in "惊青屏东":
            self.assertEqual(self.profile.get_rhyme_group(char), "十一庚")

    def test_umlaut_and_apical_i_are_normalized(self):
        self.assertEqual(get_final("绿"), "ü")
        self.assertEqual(get_final("月"), "üe")
        self.assertEqual(get_final("诗"), "-i")
        self.assertEqual(self.profile.get_rhyme_group("绿"), "十二齐")
        self.assertEqual(self.profile.get_rhyme_group("诗"), "十三支")

    def test_unknown_or_missing_rhyme_foot_cannot_pass(self):
        result = check_rhyme(
            ["惊", "青"], self.profile.rhyme_groups, expected_count=3
        )
        self.assertFalse(result["rhyme_ok"])
        self.assertEqual(result["dominant_count"], 2)

    def test_rule_loader_rejects_inconsistent_template_length(self):
        source = Path("rules/zhegutian_zhengti.json")
        data = json.loads(source.read_text(encoding="utf-8"))
        data["stanzas"][0]["lines"][0]["text_tpl"] = "平"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "text_tpl"):
                load_rule_config(path)


if __name__ == "__main__":
    unittest.main()
