"""可版本化的音韵 profile。

MVP 只实现中华新韵十四韵。接口同时约束平仄与押韵，避免未来只替换
韵部表、却仍用普通话声调判断古韵平仄的“半切换”状态。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from utils.text_utils import get_final, is_ping


@dataclass(frozen=True)
class ProsodyProfile:
    profile_id: str
    display_name: str
    rhyme_groups: Dict[str, str]

    def get_rhyme_group(self, char: str) -> str:
        if not char:
            return "未知"
        return self.rhyme_groups.get(get_final(char), "未知")

    def is_ping(self, char: str) -> bool:
        return is_ping(char)


_PROFILE_ALIASES = {
    "xinyun_14": "xinyun_14",
    "中华新韵": "xinyun_14",
    "中华新韵十四韵": "xinyun_14",
    "中华新韵（十四韵）": "xinyun_14",
}


def load_prosody_profile(profile_id: str = "xinyun_14") -> ProsodyProfile:
    canonical = _PROFILE_ALIASES.get(profile_id, profile_id)
    if canonical != "xinyun_14":
        raise ValueError(
            f"尚未实现音韵 profile: {profile_id}。当前仅支持 xinyun_14"
        )

    path = Path(__file__).parent.parent / "data" / "zhonghua_xinyun.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("profile_id") != canonical:
        raise ValueError(f"音韵数据 profile_id 不匹配：{path}")
    expected_groups = {
        "一麻",
        "二波",
        "三皆",
        "四开",
        "五微",
        "六豪",
        "七尤",
        "八寒",
        "九文",
        "十唐",
        "十一庚",
        "十二齐",
        "十三支",
        "十四姑",
    }
    actual_groups = set(data["yunbu"].values())
    if actual_groups != expected_groups:
        raise ValueError(
            "xinyun_14 韵部集合不完整："
            f"缺少 {sorted(expected_groups - actual_groups)}，"
            f"多出 {sorted(actual_groups - expected_groups)}"
        )
    return ProsodyProfile(
        profile_id=canonical,
        display_name=data["display_name"],
        rhyme_groups=data["yunbu"],
    )
