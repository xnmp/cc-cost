from __future__ import annotations

from dataclasses import dataclass

from cc_cost.domain import Cost, Provider, Session, Step, Turn
from cc_cost.pricing import PricingCatalog
from cc_cost.repository import SessionGraph


@dataclass(frozen=True, slots=True)
class TurnAnalysis:
    turn: Turn
    own_cost: Cost
    subagent_cost: Cost
    subagent_steps: int

    @property
    def total_cost(self) -> Cost:
        return self.own_cost + self.subagent_cost


@dataclass(frozen=True, slots=True)
class SessionAnalysis:
    graph: SessionGraph
    turns: tuple[TurnAnalysis, ...]
    own_cost: Cost
    subagent_cost: Cost
    subagent_steps: int
    costs_by_model: dict[str, Cost]

    @property
    def total_cost(self) -> Cost:
        return self.own_cost + self.subagent_cost


class CostAnalyzer:
    def __init__(self, graph: SessionGraph, pricing: PricingCatalog | None = None) -> None:
        self.graph = graph
        self.pricing = pricing or PricingCatalog()
        self._cost_cache: dict[str, Cost] = {}
        self._steps_cache: dict[str, int] = {}

    def step_cost(self, provider: Provider, step: Step) -> Cost:
        rule = self.pricing.rule_for(provider, step.model)
        return Cost.from_usage(step.usage, rule.price)

    def own_cost(self, session: Session) -> Cost:
        return sum(
            (self.step_cost(session.provider, step) for step in session.steps),
            start=Cost(),
        )

    def subtree_cost(self, session_id: str, visiting: frozenset[str] = frozenset()) -> Cost:
        if session_id in self._cost_cache:
            return self._cost_cache[session_id]
        if session_id in visiting:
            return Cost()
        session = self.graph.sessions[session_id]
        children = self.graph.children.get(session_id, ())
        cost = self.own_cost(session) + sum(
            (
                self.subtree_cost(child_id, visiting | {session_id})
                for child_id in children
                if child_id in self.graph.sessions
            ),
            start=Cost(),
        )
        self._cost_cache[session_id] = cost
        return cost

    def subtree_steps(self, session_id: str, visiting: frozenset[str] = frozenset()) -> int:
        if session_id in self._steps_cache:
            return self._steps_cache[session_id]
        if session_id in visiting:
            return 0
        session = self.graph.sessions[session_id]
        count = len(session.steps) + sum(
            self.subtree_steps(child_id, visiting | {session_id})
            for child_id in self.graph.children.get(session_id, ())
            if child_id in self.graph.sessions
        )
        self._steps_cache[session_id] = count
        return count

    def _children_by_turn(self, session: Session) -> dict[int, tuple[str, ...]]:
        direct = self.graph.children.get(session.id, ())
        allocated: dict[int, list[str]] = {turn.number: [] for turn in session.turns}
        if not session.turns:
            return {}

        spawn_turn = {
            spawn_id: turn.number
            for turn in session.turns
            for step in turn.steps
            for spawn_id in step.spawn_ids
        }
        starts = [
            (turn.number, turn.started_at)
            for turn in session.turns
            if turn.started_at is not None
        ]
        for child_id in direct:
            child = self.graph.sessions.get(child_id)
            if child is None:
                continue
            number = spawn_turn.get(child_id)
            if number is None and child.started_at is not None:
                eligible = [
                    turn_number
                    for turn_number, turn_start in starts
                    if turn_start is not None and turn_start <= child.started_at
                ]
                number = eligible[-1] if eligible else None
            number = number or session.turns[-1].number
            allocated[number].append(child_id)
        return {number: tuple(ids) for number, ids in allocated.items()}

    def analyze(self) -> SessionAnalysis:
        root = self.graph.root
        children_by_turn = self._children_by_turn(root)
        turn_analyses: list[TurnAnalysis] = []
        for turn in root.turns:
            own = sum(
                (self.step_cost(root.provider, step) for step in turn.steps),
                start=Cost(),
            )
            child_ids = children_by_turn.get(turn.number, ())
            subagent = sum(
                (self.subtree_cost(child_id) for child_id in child_ids),
                start=Cost(),
            )
            turn_analyses.append(
                TurnAnalysis(
                    turn=turn,
                    own_cost=own,
                    subagent_cost=subagent,
                    subagent_steps=sum(self.subtree_steps(child_id) for child_id in child_ids),
                )
            )

        direct = self.graph.children.get(root.id, ())
        costs_by_model: dict[str, Cost] = {}
        for session in self.graph.sessions.values():
            for step in session.steps:
                rule = self.pricing.rule_for(session.provider, step.model)
                costs_by_model[rule.display_name] = costs_by_model.get(
                    rule.display_name, Cost()
                ) + Cost.from_usage(step.usage, rule.price)
        return SessionAnalysis(
            graph=self.graph,
            turns=tuple(turn_analyses),
            own_cost=self.own_cost(root),
            subagent_cost=sum(
                (self.subtree_cost(child_id) for child_id in direct),
                start=Cost(),
            ),
            subagent_steps=sum(self.subtree_steps(child_id) for child_id in direct),
            costs_by_model=costs_by_model,
        )
