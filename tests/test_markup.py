from cc_cost.markup import render_assistant_markdown


def test_assistant_markdown_formats_common_message_structures() -> None:
    rendered = render_assistant_markdown(
        """## Result

This is **important** with `inline_code`.

- one
- two

> note

| name | value |
| --- | --- |
| passes | 3 |

```python
print("safe")
```

~~obsolete~~
"""
    )

    assert "<h2>Result</h2>" in rendered
    assert "<strong>important</strong>" in rendered
    assert "<code>inline_code</code>" in rendered
    assert "<ul>" in rendered
    assert "<blockquote>" in rendered
    assert "<table>" in rendered
    assert '<code class="language-python">' in rendered
    assert "<s>obsolete</s>" in rendered


def test_assistant_markdown_escapes_html_and_rejects_unsafe_links() -> None:
    rendered = render_assistant_markdown(
        '<script>alert("x")</script>\n\n[unsafe](javascript:alert("x"))'
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert 'href="javascript:' not in rendered


def test_assistant_markdown_handles_empty_malformed_and_huge_content() -> None:
    assert render_assistant_markdown("") == ""
    assert "unfinished" in render_assistant_markdown("**unfinished")

    rendered = render_assistant_markdown("x" * 100_000)

    assert rendered.startswith("<p>")
    assert rendered.endswith("</p>\n")
    assert len(rendered) > 100_000
