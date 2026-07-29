from pathlib import Path

from cc_cost.theme import read_ghostty_theme, read_terminal_theme, read_wezterm_theme


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_ghostty_theme_merges_active_theme_and_config_overrides(tmp_path: Path) -> None:
    palette = "\n".join(
        f"palette = {index}=#{index:02x}{index:02x}{index:02x}" for index in range(16)
    )
    _write(
        tmp_path / "ghostty" / "themes" / "Night",
        palette
        + """
background = #010203
foreground = #f1f2f3
selection-background = #112233
selection-foreground = #ffffff
""",
    )
    _write(
        tmp_path / "ghostty" / "config",
        "theme = Night\nforeground = #eeeeee\n",
    )

    theme = read_ghostty_theme(tmp_path)

    assert theme is not None
    assert theme.name == "Night"
    assert theme.background == "#010203"
    assert theme.foreground == "#eeeeee"
    assert theme.palette[14] == "#0e0e0e"
    assert theme.chart_colors["cache_read"] == "#0e0e0e"


def test_wezterm_reads_active_custom_scheme(tmp_path: Path) -> None:
    _write(
        tmp_path / "wezterm" / "wezterm.lua",
        """
config.color_schemes = {
  ['Night'] = {
    background = '#010203',
    foreground = '#f1f2f3',
    selection_bg = '#112233',
    selection_fg = '#ffffff',
    ansi = { '#000000', '#010101', '#020202', '#030303',
             '#040404', '#050505', '#060606', '#070707' },
    brights = { '#080808', '#090909', '#0a0a0a', '#0b0b0b',
                '#0c0c0c', '#0d0d0d', '#0e0e0e', '#0f0f0f' },
  },
}
config.color_scheme = 'Night'
""",
    )

    theme = read_wezterm_theme(tmp_path)

    assert theme is not None
    assert theme.name == "Night"
    assert theme.palette[9] == "#090909"


def test_terminal_program_controls_precedence(tmp_path: Path) -> None:
    palette = "\n".join(
        f"palette = {index}=#{index:02x}{index:02x}{index:02x}" for index in range(16)
    )
    _write(
        tmp_path / "ghostty" / "themes" / "Ghost",
        palette
        + """
background = #010203
foreground = #f1f2f3
selection-background = #112233
selection-foreground = #ffffff
""",
    )
    _write(tmp_path / "ghostty" / "config", "theme = Ghost\n")
    _write(
        tmp_path / "wezterm" / "wezterm.lua",
        """
config.color_schemes = {
  ['Wez'] = {
    background = '#111111', foreground = '#eeeeee',
    selection_bg = '#222222', selection_fg = '#ffffff',
    ansi = { '#000000', '#010101', '#020202', '#030303',
             '#040404', '#050505', '#060606', '#070707' },
    brights = { '#080808', '#090909', '#0a0a0a', '#0b0b0b',
                '#0c0c0c', '#0d0d0d', '#0e0e0e', '#0f0f0f' },
  },
}
config.color_scheme = 'Wez'
""",
    )

    assert read_terminal_theme(config_home=tmp_path, terminal_program="WezTerm").name == "Wez"
    assert read_terminal_theme(config_home=tmp_path, terminal_program="ghostty").name == "Ghost"
