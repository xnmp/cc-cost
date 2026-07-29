from __future__ import annotations

import glob
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cc_cost.content import INJECTED_CONTEXT_PREFIXES
from cc_cost.domain import Provider, Session
from cc_cost.jsonl import read_json, read_jsonl
from cc_cost.picker import SessionSummary, pick_session
from cc_cost.providers.auto import parse_session
from cc_cost.providers.claude import parse_claude_agent


def _claude_project_dir(cwd: Path, home: Path) -> Path:
    encoded = re.sub(r"[/.]", "-", str(cwd))
    return home / ".claude" / "projects" / encoded


def _codex_metadata(path: Path) -> dict[str, Any] | None:
    for event in read_jsonl(path):
        if event.get("type") == "session_meta":
            payload = event.get("payload")
            return payload if isinstance(payload, dict) else None
        if event.get("type") in {"user", "assistant"}:
            return None
    return None


def _codex_parent(metadata: dict[str, Any]) -> str | None:
    source = metadata.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    if not isinstance(spawn, dict) or not spawn.get("parent_thread_id"):
        return None
    return str(spawn["parent_thread_id"])


def _open_paths(paths: list[Path]) -> set[Path] | None:
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["lsof", "-F", "n", "--", *(str(path) for path in paths)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return {
        Path(line[1:])
        for line in result.stdout.splitlines()
        if line.startswith("n") and line[1:]
    }


def _message_text(content: object) -> str | None:
    if isinstance(content, str):
        values = [content]
    elif isinstance(content, list):
        values = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") in {"text", "input_text"}
            and isinstance(block.get("text"), str)
        ]
    else:
        return None
    for value in values:
        normalized = " ".join(value.split())
        if normalized and not normalized.startswith(INJECTED_CONTEXT_PREFIXES):
            return normalized
    return None


def _session_title(path: Path, provider: Provider) -> str:
    fallback: str | None = None
    for index, event in enumerate(read_jsonl(path)):
        if index >= 128:
            break
        if provider == "claude":
            if event.get("type") in {"ai-title", "custom-title"}:
                title = _message_text(
                    event.get("aiTitle") or event.get("customTitle") or event.get("title")
                )
                if title:
                    return title
            if event.get("type") == "user" and fallback is None:
                message = event.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                fallback = _message_text(content)
        elif event.get("type") == "session_meta":
            payload = event.get("payload")
            if isinstance(payload, dict):
                title = _message_text(payload.get("title") or payload.get("name"))
                if title:
                    return title
        elif event.get("type") == "event_msg":
            payload = event.get("payload")
            if isinstance(payload, dict) and payload.get("type") == "user_message":
                title = _message_text(payload.get("message"))
                if title:
                    return title
        elif event.get("type") == "response_item":
            payload = event.get("payload")
            if (
                isinstance(payload, dict)
                and payload.get("type") == "message"
                and payload.get("role") == "user"
            ):
                title = _message_text(payload.get("content"))
                if title:
                    return title
    return fallback or "(untitled session)"


def _provider(path: Path) -> Provider:
    return "codex" if path.name.startswith("rollout-") else "claude"


@dataclass(frozen=True, slots=True)
class SessionGraph:
    root: Session
    sessions: dict[str, Session]
    children: dict[str, tuple[str, ...]]


class SessionRepository:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()

    def candidates(self, cwd: Path) -> list[Path]:
        claude = list(_claude_project_dir(cwd, self.home).glob("*.jsonl"))
        codex: list[Path] = []
        for path in (self.home / ".codex" / "sessions").glob("*/*/*/*.jsonl"):
            metadata = _codex_metadata(path)
            if (
                metadata
                and metadata.get("cwd") == str(cwd)
                and _codex_parent(metadata) is None
                and metadata.get("thread_source") != "subagent"
            ):
                codex.append(path)
        return sorted(claude + codex, key=lambda path: path.stat().st_mtime, reverse=True)

    def choose(self, paths: list[Path]) -> Path:
        if not paths:
            raise FileNotFoundError("no Claude Code or Codex transcript found")
        open_paths = _open_paths(paths)
        running = [path for path in paths if open_paths is not None and path in open_paths]
        if len(running) == 1:
            return running[0]
        if len(paths) == 1 or not os.isatty(0):
            return paths[0]
        summaries = []
        for path in paths:
            stat = path.stat()
            provider = _provider(path)
            summaries.append(
                SessionSummary(
                    path=path,
                    provider=provider,
                    title=_session_title(path, provider),
                    modified_at=stat.st_mtime,
                    size=stat.st_size,
                    running=path in running,
                )
            )
        return pick_session(summaries)

    def related(self, root_path: Path) -> SessionGraph:
        root = parse_session(root_path)
        if root.provider == "codex":
            return self._codex_graph(root)
        return self._claude_graph(root)

    def _codex_graph(self, root: Session) -> SessionGraph:
        indexed: dict[str, tuple[Path, str | None]] = {}
        for path in (self.home / ".codex" / "sessions").glob("*/*/*/*.jsonl"):
            metadata = _codex_metadata(path)
            if not metadata:
                continue
            session_id = str(metadata.get("id") or metadata.get("session_id") or path.stem)
            indexed[session_id] = (path, _codex_parent(metadata))

        sessions = {root.id: root}
        children: dict[str, list[str]] = defaultdict(list)
        pending = [root.id]
        while pending:
            parent_id = pending.pop()
            for session_id, (path, candidate_parent) in indexed.items():
                if candidate_parent != parent_id or session_id in sessions:
                    continue
                child = parse_session(path)
                sessions[session_id] = child
                children[parent_id].append(session_id)
                pending.append(session_id)
        return SessionGraph(
            root=root,
            sessions=sessions,
            children={key: tuple(value) for key, value in children.items()},
        )

    def _claude_graph(self, root: Session) -> SessionGraph:
        base = root.path.with_suffix("")
        subagents = base / "subagents"
        sessions = {root.id: root}
        spawn_parent: dict[str, str] = {}
        for session in [root]:
            for step in session.steps:
                for spawn_id in step.spawn_ids:
                    spawn_parent[spawn_id] = session.id

        unparented: list[Session] = []
        for meta_path_text in sorted(glob.glob(str(subagents / "agent-*.meta.json"))):
            meta_path = Path(meta_path_text)
            metadata = read_json(meta_path)
            if not metadata or not metadata.get("toolUseId"):
                continue
            jsonl_path = Path(str(meta_path)[: -len(".meta.json")] + ".jsonl")
            if not jsonl_path.exists():
                continue
            tool_use_id = str(metadata["toolUseId"])
            child = parse_claude_agent(
                jsonl_path,
                tool_use_id=tool_use_id,
                label=str(metadata.get("description") or metadata.get("agentType") or "agent"),
            )
            sessions[tool_use_id] = child
            unparented.append(child)
            for step in child.steps:
                for spawn_id in step.spawn_ids:
                    spawn_parent[spawn_id] = child.id

        children: dict[str, list[str]] = defaultdict(list)
        for child in unparented:
            parent = spawn_parent.get(child.id, root.id)
            children[parent].append(child.id)
        return SessionGraph(
            root=root,
            sessions=sessions,
            children={key: tuple(value) for key, value in children.items()},
        )
