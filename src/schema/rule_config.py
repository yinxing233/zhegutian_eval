# src/schema/rule_config.py

"""
这个文件定义“词牌规则”的结构（schema）。

核心原则：
- JSON 只存“数据”
- 这里定义“结构 + 字段含义”
- 其他模块（evaluator / metrics）只依赖这里的结构，而不直接依赖 JSON

可以把这个文件理解为：整个规则系统的“数据接口层”
"""

import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


class Line(BaseModel):
    """
    单句规则（最小单位）

    对应 JSON 中 stanzas[].lines[] 的一个元素
    描述“一句词应该长什么样”
    """

    index: int = Field(..., description="行序号（全词范围，从1开始）")

    char_count: int = Field(..., description="该句字数，例如 7 或 3")

    text_tpl: str = Field(
        ...,
        description="平仄模板，例如：中仄平平中仄平"
    )

    rhyme: bool = Field(
        ...,
        description="该句是否参与押韵（True 表示需要押韵）"
    )

    rhyme_role: Optional[str] = Field(
        None,
        description="押韵角色，例如：起韵；不是所有句子都有"
    )

    strict_positions: List[int] = Field(
        ...,
        description="必须严格匹配平仄的位置（从1开始计数）"
    )

    tail_strict_pingze: bool = Field(
        ...,
        description="句尾是否必须符合平仄规则（有些词牌句尾更严格）"
    )

    tail_rhyme: bool = Field(
        ...,
        description="句尾是否必须押韵（通常与 rhyme 配合使用）"
    )


class Stanza(BaseModel):
    """
    段（上阕 / 下阕）

    一组句子的集合
    """

    section: str = Field(
        ...,
        description="段名，例如：上阕 / 下阕"
    )

    lines: List[Line] = Field(
        ...,
        description="该段包含的所有句子"
    )


class AntithesisItem(BaseModel):
    """
    单条对仗规则

    描述哪几句之间需要对仗，以及强度
    """

    pair: List[int] = Field(
        ...,
        description="需要对仗的句子编号，例如 [3, 4]"
    )

    desc: str = Field(
        ...,
        description="规则说明（给人读）"
    )

    type: str = Field(
        ...,
        description="规则类型：strict（必须）或 soft（建议）"
    )

    weight: float = Field(
        ...,
        description="该规则在评分中的权重"
    )


class Antithesis(BaseModel):
    """
    对仗规则集合

    分为：
    - required：必须满足
    - recommended：建议满足
    """

    required: List[AntithesisItem] = Field(
        ...,
        description="必须满足的对仗规则"
    )

    recommended: List[AntithesisItem] = Field(
        ...,
        description="推荐满足的对仗规则"
    )


class SpecialRules(BaseModel):
    """
    特殊规则入口

    未来可以扩展更多规则（不仅限于对仗）
    """

    antithesis: Antithesis = Field(
        ...,
        description="对仗规则"
    )


class RuleConfig(BaseModel):
    """
    整个词牌规则的顶层结构

    对应一个完整的 JSON 文件（例如 鹧鸪天·正体）
    """

    cipai: str = Field(
        ...,
        description="词牌名，例如：鹧鸪天"
    )

    variant: str = Field(
        ...,
        description="体例说明，例如：正体（晏几道体）"
    )

    total_chars: int = Field(
        ...,
        description="全词总字数（用于整体校验）"
    )

    source: str = Field(
        ...,
        description="出处，例如：《钦定词谱》"
    )

    rhyme_book: str = Field(
        ...,
        description="使用的韵书，例如：词林正韵"
    )

    symbol_def: dict = Field(
        ...,
        description="平仄符号定义（平 / 仄 / 中 的解释）"
    )

    stanzas: List[Stanza] = Field(
        ...,
        description="分段结构（上阕 / 下阕）"
    )

    special_rules: SpecialRules = Field(
        ...,
        description="额外规则（如对仗）"
    )


def load_rule_config(path: str | Path) -> RuleConfig:
    """
    从 JSON 文件加载规则，并进行结构校验

    使用方式：
        rule = load_rule_config("rules/zhegutian_zhengti.json")

    返回：
        RuleConfig 对象（而不是 dict）
    """

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 这里会自动做：
    # - 字段是否存在
    # - 类型是否正确
    # - 嵌套结构是否匹配
    return RuleConfig(**data)