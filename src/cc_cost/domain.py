from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

Provider = Literal["claude", "codex"]
ContentKind = Literal["message", "reasoning", "tool_call", "tool_result", "system"]
ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Provider-neutral billable token quantities for one model invocation."""

    input: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    output: int = 0

    def __post_init__(self) -> None:
        if min(
            self.input,
            self.cache_read,
            self.cache_write_5m,
            self.cache_write_1h,
            self.output,
        ) < 0:
            raise ValueError("token counts must be non-negative")

    @property
    def cache_write(self) -> int:
        return self.cache_write_5m + self.cache_write_1h

    @property
    def total(self) -> int:
        return self.input + self.cache_read + self.cache_write + self.output


@dataclass(frozen=True, slots=True)
class ContentBlock:
    role: str
    kind: ContentKind
    text: str
    label: str = ""
    call_id: str = ""


@dataclass(frozen=True, slots=True)
class PassTrace:
    input: tuple[ContentBlock, ...] = ()
    output: tuple[ContentBlock, ...] = ()
    cached_preview: tuple[ContentBlock, ...] = ()
    cached_preview_truncated: bool = False


@dataclass(frozen=True, slots=True)
class Step:
    model: str
    usage: TokenUsage
    spawn_ids: tuple[str, ...] = ()
    subagent: bool = False
    trace: PassTrace = PassTrace()


@dataclass(frozen=True, slots=True)
class Turn:
    number: int
    steps: tuple[Step, ...]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    provider: Provider
    path: Path
    cwd: Path | None
    started_at: datetime | None
    turns: tuple[Turn, ...]
    parent_id: str | None = None
    label: str = ""

    @property
    def steps(self) -> tuple[Step, ...]:
        return tuple(step for turn in self.turns for step in turn.steps)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per one million tokens."""

    input: Decimal
    cache_read: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    output: Decimal


@dataclass(frozen=True, slots=True)
class Cost:
    input: Decimal = ZERO
    cache_read: Decimal = ZERO
    cache_write: Decimal = ZERO
    output: Decimal = ZERO

    @classmethod
    def from_usage(cls, usage: TokenUsage, price: ModelPrice) -> Cost:
        million = Decimal(1_000_000)
        return cls(
            input=Decimal(usage.input) * price.input / million,
            cache_read=Decimal(usage.cache_read) * price.cache_read / million,
            cache_write=(
                Decimal(usage.cache_write_5m) * price.cache_write_5m
                + Decimal(usage.cache_write_1h) * price.cache_write_1h
            )
            / million,
            output=Decimal(usage.output) * price.output / million,
        )

    def __add__(self, other: Cost) -> Cost:
        return Cost(
            input=self.input + other.input,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
            output=self.output + other.output,
        )

    @property
    def total(self) -> Decimal:
        return self.input + self.cache_read + self.cache_write + self.output

    def as_floats(self) -> dict[str, float]:
        return {
            "cache_read": float(self.cache_read),
            "cache_write": float(self.cache_write),
            "output": float(self.output),
            "input": float(self.input),
        }
