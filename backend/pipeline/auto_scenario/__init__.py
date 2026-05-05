"""
AutoScenario — GPT APIによる自動シナリオ生成

チャンネルのtheme_seedsとcontent_policyを元に
yukkuri対話 / monologue 両スタイルのシナリオを自動生成する。
"""

from .generator import ScenarioGenerator

__all__ = ["ScenarioGenerator"]
