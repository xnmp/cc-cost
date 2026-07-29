from cc_cost.content import tail
from cc_cost.domain import ContentBlock


def test_cached_context_preview_keeps_only_the_bounded_tail() -> None:
    blocks = (
        ContentBlock("developer", "system", "a" * 6_000),
        ContentBlock("user", "message", "b" * 6_000),
    )

    preview, truncated = tail(blocks, limit=8_000)

    assert truncated is True
    assert sum(len(item.text.removeprefix("… ")) for item in preview) == 8_000
    assert preview[0].text.startswith("… ")
    assert preview[-1].text == "b" * 6_000
