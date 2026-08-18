from __future__ import annotations

from cascade.application.copilot.translator import Nl2SqlTranslator
from cascade.infrastructure.config import Settings
from cascade.infrastructure.copilot.llm import LlmTranslator
from cascade.infrastructure.copilot.rule_based import RuleBasedTranslator


def build_translator(settings: Settings) -> Nl2SqlTranslator:
    if settings.copilot_api_url and settings.copilot_api_key:
        return LlmTranslator(
            settings.copilot_api_url,
            settings.copilot_api_key,
            settings.copilot_model,
        )
    return RuleBasedTranslator()
