from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cc_cost.domain import ModelPrice, Provider


class UnknownModelError(ValueError):
    pass


def _price(
    input: str,
    output: str,
    cache_read: str,
    cache_write_5m: str,
    cache_write_1h: str | None = None,
) -> ModelPrice:
    return ModelPrice(
        input=Decimal(input),
        output=Decimal(output),
        cache_read=Decimal(cache_read),
        cache_write_5m=Decimal(cache_write_5m),
        cache_write_1h=Decimal(cache_write_1h or cache_write_5m),
    )


@dataclass(frozen=True, slots=True)
class PriceRule:
    provider: Provider
    model_contains: str
    display_name: str
    price: ModelPrice

    def matches(self, provider: Provider, model: str) -> bool:
        return self.provider == provider and self.model_contains in model.casefold()


# Claude rates preserve the original script's behavior. OpenAI GPT-5.6 rates
# are standard API equivalents; Codex subscriptions are not pay-as-you-go bills.
DEFAULT_RULES = (
    PriceRule("claude", "fable", "Fable", _price("10", "50", "1", "12.5", "20")),
    PriceRule("claude", "opus", "Opus", _price("5", "25", "0.5", "6.25", "10")),
    PriceRule("claude", "sonnet", "Sonnet", _price("3", "15", "0.3", "3.75", "6")),
    PriceRule("claude", "haiku", "Haiku", _price("1", "5", "0.1", "1.25", "2")),
    PriceRule("codex", "gpt-5.6-sol", "GPT-5.6 Sol", _price("5", "30", "0.5", "6.25")),
    PriceRule(
        "codex", "gpt-5.6-terra", "GPT-5.6 Terra", _price("2.5", "15", "0.25", "3.125")
    ),
    PriceRule("codex", "gpt-5.6-luna", "GPT-5.6 Luna", _price("1", "6", "0.1", "1.25")),
)


@dataclass(frozen=True, slots=True)
class PricingCatalog:
    rules: tuple[PriceRule, ...] = DEFAULT_RULES

    def rule_for(self, provider: Provider, model: str) -> PriceRule:
        normalized = model.casefold()
        for rule in self.rules:
            if rule.matches(provider, normalized):
                return rule
        raise UnknownModelError(
            f"no {provider} price configured for model {model!r}; "
            "refusing to silently estimate with another model"
        )
