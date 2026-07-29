from __future__ import annotations

from markdown_it import MarkdownIt

_MARKDOWN = MarkdownIt(
    "commonmark",
    {
        "html": False,
        "linkify": False,
        "typographer": False,
    },
).enable(("strikethrough", "table"))


def render_assistant_markdown(text: str) -> str:
    """Render untrusted assistant Markdown without permitting raw HTML."""
    return _MARKDOWN.render(text)
