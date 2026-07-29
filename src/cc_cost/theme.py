from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class TerminalTheme:
    name: str
    source: str
    background: str
    foreground: str
    selection_background: str
    selection_foreground: str
    palette: tuple[str, ...]

    @property
    def chart_colors(self) -> dict[str, str]:
        return {
            "cache_read": self.palette[14],
            "cache_write": self.palette[13],
            "output": self.palette[12],
            "input": self.palette[8],
            "steps": self.palette[9],
            "fallback_subagent": self.palette[5],
        }

    @property
    def model_colors(self) -> tuple[str, ...]:
        return tuple(self.palette[index] for index in (9, 11, 13, 14, 10, 12))

    @classmethod
    def system(cls) -> TerminalTheme:
        """CSS system-color fallback when no terminal palette can be read."""
        return cls(
            name="System",
            source="browser system colors",
            background="Canvas",
            foreground="CanvasText",
            selection_background="Highlight",
            selection_foreground="HighlightText",
            palette=(
                "CanvasText",
                "LinkText",
                "Mark",
                "MarkText",
                "AccentColor",
                "VisitedText",
                "Highlight",
                "CanvasText",
                "GrayText",
                "LinkText",
                "Mark",
                "MarkText",
                "AccentColor",
                "VisitedText",
                "Highlight",
                "CanvasText",
            ),
        )


def _assignment(line: str) -> tuple[str, str] | None:
    content = line.strip()
    if not content or content.startswith("#"):
        return None
    if "=" not in content:
        return None
    key, value = (part.strip() for part in content.split("=", 1))
    return key, value


def _ghostty_values(path: Path) -> tuple[dict[str, str], dict[int, str]]:
    values: dict[str, str] = {}
    palette: dict[int, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values, palette
    for line in lines:
        parsed = _assignment(line)
        if parsed is None:
            continue
        key, value = parsed
        if key == "palette" and "=" in value:
            index_text, color = (part.strip() for part in value.split("=", 1))
            if index_text.isdigit() and _HEX.fullmatch(color):
                palette[int(index_text)] = color
        elif value:
            values[key] = value
    return values, palette


def read_ghostty_theme(config_home: Path) -> TerminalTheme | None:
    ghostty = config_home / "ghostty"
    config_values, config_palette = _ghostty_values(ghostty / "config")
    name = config_values.get("theme", "").strip()
    if not name:
        return None
    theme_values, theme_palette = _ghostty_values(ghostty / "themes" / name)
    values = theme_values | config_values
    palette = theme_palette | config_palette
    colors = tuple(palette.get(index, "") for index in range(16))
    required = (
        values.get("background"),
        values.get("foreground"),
        values.get("selection-background"),
        values.get("selection-foreground"),
        *colors,
    )
    if not all(value and (_HEX.fullmatch(value) is not None) for value in required):
        return None
    return TerminalTheme(
        name=name,
        source=str(ghostty / "themes" / name),
        background=values["background"],
        foreground=values["foreground"],
        selection_background=values["selection-background"],
        selection_foreground=values["selection-foreground"],
        palette=colors,
    )


def _lua_color(block: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*['\"](#[0-9a-fA-F]{{6}})['\"]", block)
    return match.group(1) if match else None


def _lua_palette(block: str, key: str) -> tuple[str, ...]:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*\{{([^}}]+)\}}", block, re.DOTALL)
    if not match:
        return ()
    return tuple(re.findall(r"['\"](#[0-9a-fA-F]{6})['\"]", match.group(1)))


def read_wezterm_theme(config_home: Path) -> TerminalTheme | None:
    path = config_home / "wezterm" / "wezterm.lua"
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    active = re.search(r"\bconfig\.color_scheme\s*=\s*['\"]([^'\"]+)['\"]", source)
    if not active:
        return None
    name = active.group(1)
    start = re.search(rf"\[['\"]{re.escape(name)}['\"]\]\s*=\s*\{{", source)
    if not start:
        return None
    tail = source[start.end() :]
    end = re.search(r"\n\s*\},", tail)
    if not end:
        return None
    block = tail[: end.start()]
    ansi = _lua_palette(block, "ansi")
    brights = _lua_palette(block, "brights")
    background = _lua_color(block, "background")
    foreground = _lua_color(block, "foreground")
    selection_background = _lua_color(block, "selection_bg")
    selection_foreground = _lua_color(block, "selection_fg")
    if (
        not background
        or not foreground
        or not selection_background
        or not selection_foreground
        or len(ansi) != 8
        or len(brights) != 8
    ):
        return None
    return TerminalTheme(
        name=name,
        source=str(path),
        background=background,
        foreground=foreground,
        selection_background=selection_background,
        selection_foreground=selection_foreground,
        palette=ansi + brights,
    )


def read_terminal_theme(
    *,
    config_home: Path | None = None,
    terminal_program: str | None = None,
) -> TerminalTheme:
    root = config_home or Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    )
    terminal = (terminal_program or os.environ.get("TERM_PROGRAM", "")).casefold()
    readers = (
        (read_wezterm_theme, read_ghostty_theme)
        if "wezterm" in terminal
        else (read_ghostty_theme, read_wezterm_theme)
    )
    for reader in readers:
        theme = reader(root)
        if theme is not None:
            return theme
    return TerminalTheme.system()
