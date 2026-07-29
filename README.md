# cc-cost

`cc-cost` reads Claude Code and Codex JSONL transcripts, computes token costs,
prints a per-turn terminal summary, and writes a self-contained interactive HTML
chart. It does not call a model or upload transcript content.

Claude and Codex use the same report UI:

- per-turn and per-pass views
- normalized or raw cost bars
- component and subagent segments
- nested subagent drill-down with breadcrumbs
- click or keyboard-open chart segments to inspect associated transcript content
- minimap selection, cursor-centered zoom, and keyboard reset
- terminal-theme colors read from Ghostty or WezTerm

Session discovery opens a searchable, keyboard-selectable list with human-readable
titles. Use arrow keys or PageUp/PageDown to move through every matching session,
type to filter by title, and press Enter to select.

## Content inspector

Select an input, output, cache-read, or cache-write segment to see its exact
provider-reported token count and the readable transcript blocks associated with
each contributing pass. Messages, reasoning summaries, tool calls, and tool
results are formatted separately.

Provider transcripts do not contain token IDs, the complete provider-assembled
prompt, or exact cache boundaries. Cached segments therefore show a bounded
preview of the recorded context—roughly the last 2,000 tokens per pass—and label
that limitation in the report.

The generated HTML is local and self-contained, but it now embeds these transcript
excerpts. Treat the report as sensitive and do not publish it without reviewing
its contents.

## Why it has a domain model

Claude and Codex expose different event schemas:

- Claude attaches usage to assistant messages and stores spawned agents beside
  the root transcript.
- Codex emits cumulative token snapshots and stores spawned agents as separate
  sessions linked by `parent_thread_id`.

Provider adapters normalize both formats into immutable `Session`, `Turn`,
`Step`, and `TokenUsage` values. Pricing and reporting operate only on that
provider-neutral model. This prevents transcript details from leaking into cost
arithmetic or presentation.

## Install

```console
uv tool install .
```

For development:

```console
uv sync
uv run pytest
uv run pyrefly check
uv run ruff check .
```

## Use

Discover the current directory's active or newest Claude/Codex session:

```console
cc-cost
```

Analyze an explicit transcript without opening a browser:

```console
cc-cost --no-open ~/.codex/sessions/2026/07/29/rollout-….jsonl
```

Write the report somewhere specific:

```console
cc-cost -o ./session-cost.html transcript.jsonl
```

Set `CC_COST_OPEN=0` to disable browser opening by default.

## Terminal theme

At report generation time, `cc-cost` reads the active terminal palette:

1. If `TERM_PROGRAM` identifies WezTerm, read its active custom
   `config.color_scheme`; otherwise prefer Ghostty.
2. For Ghostty, read `~/.config/ghostty/config`, load its active `theme` file,
   and apply config-level color and palette overrides.
3. If the preferred terminal cannot be parsed, try the other terminal.
4. If neither exposes a complete palette, use browser system colors.

The palette drives page surfaces, text, selection, chart components, model
segments, focus outlines, and tooltips. The generated report records the theme
name and source path in its footer.

## Cost semantics

Claude prices preserve the original script's model-family rates. Codex prices
are standard API-equivalent estimates for GPT-5.6 Sol, Terra, and Luna:

| Model | Input | Cached input | Cache write | Output |
|---|---:|---:|---:|---:|
| GPT-5.6 Sol | $5.00 | $0.50 | $6.25 | $30.00 |
| GPT-5.6 Terra | $2.50 | $0.25 | $3.125 | $15.00 |
| GPT-5.6 Luna | $1.00 | $0.10 | $1.25 | $6.00 |

Rates are USD per million tokens. Codex may be covered by a subscription, so
the report is not an invoice. Unknown models fail explicitly instead of being
silently priced as a different model.

GPT-5.6 rates come from OpenAI's
[model comparison](https://developers.openai.com/api/docs/models/compare).
For GPT-5.6, cache writes cost 1.25× uncached input and cache reads cost 10%.

Codex's `input_tokens` includes cached and cache-write tokens. The adapter
subtracts those quantities before applying the uncached input rate. Repeated
cumulative snapshots are deduplicated.

## Project layout

- `domain.py`: provider-neutral immutable values and cost arithmetic
- `providers/`: Claude and Codex transcript adapters
- `repository.py`: discovery and subagent graph reconstruction
- `analysis.py`: pure session/tree cost aggregation
- `chart.py`: provider-neutral interactive chart contract
- `theme.py`: Ghostty and WezTerm palette adapters
- `interactive_report.py`: shared accessible HTML/SVG presenter
- `report.py`: terminal presenter and HTML entry point
- `cli.py`: command-line infrastructure
