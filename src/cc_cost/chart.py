from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from cc_cost.analysis import CostAnalyzer, SessionAnalysis
from cc_cost.content import is_prompt_context
from cc_cost.domain import ContentBlock, Cost, Session, Step
from cc_cost.markup import render_assistant_markdown
from cc_cost.pricing import PricingCatalog


def _sum_cost(costs: Iterable[Cost]) -> Cost:
    return sum(costs, start=Cost())


def build_chart(
    analysis: SessionAnalysis,
    model_palette: tuple[str, ...],
    pricing: PricingCatalog | None = None,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, str],
    tuple[str, ...],
]:
    """Translate provider-neutral sessions into the original interactive chart contract."""
    catalog = pricing or PricingCatalog()
    graph = analysis.graph
    analyzer = CostAnalyzer(graph, catalog)

    def step_cost(session: Session, step: Step) -> Cost:
        return analyzer.step_cost(session.provider, step)

    def model_name(session: Session, step: Step) -> str:
        return catalog.rule_for(session.provider, step.model).display_name

    def costs_by_model(session_id: str, visiting: frozenset[str] = frozenset()) -> dict[str, Cost]:
        if session_id in visiting:
            return {}
        session = graph.sessions[session_id]
        result: dict[str, Cost] = {}
        for step in session.steps:
            name = model_name(session, step)
            result[name] = result.get(name, Cost()) + step_cost(session, step)
        for child_id in graph.children.get(session_id, ()):
            if child_id not in graph.sessions:
                continue
            for name, cost in costs_by_model(child_id, visiting | {session_id}).items():
                result[name] = result.get(name, Cost()) + cost
        return result

    all_models = tuple(
        dict.fromkeys(
            model_name(session, step)
            for session in graph.sessions.values()
            for step in session.steps
        )
    )
    model_colors = {
        model: model_palette[index % len(model_palette)]
        for index, model in enumerate(all_models)
    }
    pass_details: dict[str, dict[str, Any]] = {}

    def content(item: ContentBlock) -> dict[str, Any]:
        return {
            "role": item.role,
            "kind": item.kind,
            "text": item.text,
            "label": item.label,
            "call_id": item.call_id,
            "html": (
                render_assistant_markdown(item.text)
                if item.role == "assistant" and item.kind == "message"
                else ""
            ),
            "prompt_context": is_prompt_context(item),
        }

    def pass_id(session: Session, index: int) -> str:
        key = f"{session.id}:{index}"
        step = session.steps[index]
        pass_details[key] = {
            "model": model_name(session, step),
            "usage": {
                "input": step.usage.input,
                "cache_read": step.usage.cache_read,
                "cache_write": step.usage.cache_write,
                "output": step.usage.output,
            },
            "input": [content(item) for item in step.trace.input],
            "output": [content(item) for item in step.trace.output],
            "cached": [content(item) for item in step.trace.cached_preview],
            "cached_truncated": step.trace.cached_preview_truncated,
        }
        return key

    def dominant(session_id: str) -> str | None:
        by_model = costs_by_model(session_id)
        return max(by_model, key=lambda name: by_model[name].total) if by_model else None

    def segment(session_id: str) -> dict[str, Any]:
        session = graph.sessions[session_id]
        return {
            "id": session_id,
            "label": session.label or "agent",
            "model": dominant(session_id),
            "total": float(analyzer.subtree_cost(session_id).total),
        }

    def submodel(child_ids: Iterable[str]) -> dict[str, float]:
        totals: dict[str, Cost] = {}
        for child_id in child_ids:
            if child_id not in graph.sessions:
                continue
            for name, cost in costs_by_model(child_id).items():
                totals[name] = totals.get(name, Cost()) + cost
        return {name: float(cost.total) for name, cost in totals.items()}

    def children_by_step(session: Session) -> dict[int, tuple[str, ...]]:
        direct = graph.children.get(session.id, ())
        positions = {
            spawn_id: index
            for index, step in enumerate(session.steps)
            for spawn_id in step.spawn_ids
        }
        allocated: dict[int, list[str]] = defaultdict(list)
        fallback = max(0, len(session.steps) - 1)
        for child_id in direct:
            allocated[positions.get(child_id, fallback)].append(child_id)
        return {index: tuple(ids) for index, ids in allocated.items()}

    nodes: dict[str, dict[str, Any]] = {}
    for session_id, session in graph.sessions.items():
        if session_id == graph.root.id:
            continue
        step_children = children_by_step(session)
        bars = []
        for index, step in enumerate(session.steps):
            cost = step_cost(session, step)
            children = tuple(
                child_id
                for child_id in step_children.get(index, ())
                if child_id in graph.sessions
            )
            bars.append(
                {
                    "label": str(index + 1),
                    "comps": cost.as_floats(),
                    "steps": 1,
                    "subs": [segment(child_id) for child_id in children],
                    "pass_ids": [pass_id(session, index)],
                }
            )
        direct = graph.children.get(session_id, ())
        own = analyzer.own_cost(session)
        rolled = analyzer.subtree_cost(session_id)
        nodes[session_id] = {
            "title": "subagent",
            "subtitle": session.label,
            "model": dominant(session_id),
            "kind": "pass",
            "total": float(rolled.total),
            "steps": len(session.steps),
            "sub_steps": analyzer.subtree_steps(session_id) - len(session.steps),
            "comp_tot": own.as_floats(),
            "submodel": submodel(direct),
            "bars": bars,
        }

    root = graph.root
    by_turn = analyzer.children_by_turn(root)
    turn_bars: list[dict[str, Any]] = []
    root_step_bars: list[dict[str, Any]] = []
    all_direct: list[str] = []
    root_pass_index = 0
    for turn in root.turns:
        if not turn.steps:
            continue
        turn_pass_indexes = tuple(
            range(root_pass_index, root_pass_index + len(turn.steps))
        )
        root_pass_index += len(turn.steps)
        direct = tuple(
            child_id
            for child_id in by_turn.get(turn.number, ())
            if child_id in graph.sessions
        )
        all_direct.extend(direct)
        own = _sum_cost(step_cost(root, step) for step in turn.steps)
        turn_bars.append(
            {
                "label": str(turn.number),
                "comps": own.as_floats(),
                "steps": len(turn.steps),
                "subs": [segment(child_id) for child_id in direct],
                "pass_ids": [pass_id(root, index) for index in turn_pass_indexes],
            }
        )
        exact = {
            spawn_id: index
            for index, step in enumerate(turn.steps)
            for spawn_id in step.spawn_ids
        }
        allocated: dict[int, list[str]] = defaultdict(list)
        fallback = len(turn.steps) - 1
        for child_id in direct:
            allocated[exact.get(child_id, fallback)].append(child_id)
        for index, (step, session_index) in enumerate(
            zip(turn.steps, turn_pass_indexes, strict=True)
        ):
            children = allocated.get(index, ())
            root_step_bars.append(
                {
                    "label": f"{turn.number}.{index + 1}",
                    "comps": step_cost(root, step).as_floats(),
                    "steps": 1,
                    "subs": [segment(child_id) for child_id in children],
                    "pass_ids": [pass_id(root, session_index)],
                }
            )

    root_total = analysis.total_cost
    nodes["root"] = {
        "title": "Session cost by turn",
        "subtitle": root.provider.title(),
        "model": dominant(root.id),
        "kind": "turn",
        "total": float(root_total.total),
        "steps": len(root.steps),
        "sub_steps": analysis.subagent_steps,
        "comp_tot": analysis.own_cost.as_floats(),
        "submodel": submodel(all_direct),
        "bars": turn_bars,
    }
    nodes["root_steps"] = {
        "title": "Session cost by pass",
        "subtitle": root.provider.title(),
        "model": nodes["root"]["model"],
        "kind": "pass",
        "total": float(root_total.total),
        "steps": len(root.steps),
        "sub_steps": analysis.subagent_steps,
        "comp_tot": analysis.own_cost.as_floats(),
        "submodel": submodel(all_direct),
        "bars": root_step_bars,
    }
    return nodes, pass_details, model_colors, all_models
