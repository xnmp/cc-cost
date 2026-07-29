from decimal import Decimal

import pytest

from cc_cost.domain import Cost, ModelPrice, TokenUsage
from cc_cost.pricing import PricingCatalog, UnknownModelError


def test_cost_prices_each_component_independently() -> None:
    usage = TokenUsage(
        input=1_000_000,
        cache_read=2_000_000,
        cache_write_5m=3,
        cache_write_1h=2,
        output=4,
    )
    price = ModelPrice(
        input=Decimal("5"),
        cache_read=Decimal("0.5"),
        cache_write_5m=Decimal("6.25"),
        cache_write_1h=Decimal("10"),
        output=Decimal("30"),
    )

    cost = Cost.from_usage(usage, price)

    assert cost.input == Decimal("5")
    assert cost.cache_read == Decimal("1")
    assert cost.cache_write == Decimal("0.00003875")
    assert cost.output == Decimal("0.00012")
    assert cost.total == Decimal("6.00015875")


@pytest.mark.parametrize(
    "field", ["input", "cache_read", "cache_write_5m", "cache_write_1h", "output"]
)
def test_usage_rejects_negative_tokens(field: str) -> None:
    values = {
        "input": 0,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
        "output": 0,
    }
    values[field] = -1

    with pytest.raises(ValueError, match="non-negative"):
        TokenUsage(**values)


def test_unknown_model_fails_instead_of_using_a_default_price() -> None:
    with pytest.raises(UnknownModelError, match="unknown-model"):
        PricingCatalog().rule_for("codex", "unknown-model")


def test_pricing_matches_model_snapshot_suffixes() -> None:
    rule = PricingCatalog().rule_for("codex", "gpt-5.6-terra-2026-07-01")

    assert rule.display_name == "GPT-5.6 Terra"
    assert rule.price.output == Decimal("15")
