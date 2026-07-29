import pytest

from cc_cost.content import is_prompt_context, tail
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


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        (ContentBlock("developer", "message", "base instructions"), True),
        (ContentBlock("system", "message", "system instructions"), True),
        (ContentBlock("user", "system", "legacy system instructions"), True),
        (ContentBlock("user", "message", "# AGENTS.md instructions\n..."), True),
        (ContentBlock("user", "message", "  <environment_context>...</environment_context>"), True),
        (ContentBlock("user", "message", "<skills_instructions>...</skills_instructions>"), True),
        (ContentBlock("user", "message", "Please inspect the environment_context"), False),
        (ContentBlock("assistant", "message", "# AGENTS.md instructions"), False),
    ],
)
def test_prompt_context_distinguishes_injected_setup_from_human_messages(
    block: ContentBlock,
    expected: bool,
) -> None:
    assert is_prompt_context(block) is expected
