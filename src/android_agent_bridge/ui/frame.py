"""Compact, agent-oriented representation of an Android screen."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .parser import UINode, UITree


@dataclass(slots=True)
class Action:
    number: int
    verb: str
    label: str
    kind: str
    node: UINode | None = field(default=None, repr=False)
    action_id: str | None = None

    def prompt(self) -> str:
        return f"{self.number} {self.label}"


@dataclass(slots=True)
class Frame:
    app: str
    screen: str
    read: list[str]
    actions: list[Action]
    page: int = 1
    total_pages: int = 1

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "app": self.app,
            "screen": self.screen,
            "read": self.read,
            "do": [action.prompt() for action in self.actions],
            "pick": 'act with: ui do <n>   (e.g. ui do 1 "your text")',
        }
        if self.total_pages > 1:
            result["page"] = f"{self.page}/{self.total_pages}"
        return result


class FrameBuilder:
    """Build frames without exposing coordinates or raw XML to the agent."""

    _submit = re.compile(
        r"^(send|submit|post|reply|publish|search|go|done|next|confirm|ok|buscar|enviar|aceptar)\b",
        re.IGNORECASE,
    )
    _status = re.compile(
        r"^(\d{1,2}:\d{2}|delivered|read|sent|sending|seen|online|typing\.\.\.)$", re.IGNORECASE
    )

    def __init__(self, *, page_size: int = 8, read_cap: int = 12) -> None:
        self.page_size = page_size
        self.read_cap = read_cap

    def build(
        self,
        tree: UITree,
        *,
        app: str = "unknown",
        screen: str = "unknown",
        page: int = 1,
        knowledge_actions: Sequence[Action] = (),
    ) -> Frame:
        inputs: list[UINode] = []
        controls: list[UINode] = []
        opens: list[UINode] = []
        readable: list[str] = []
        scroll_node: UINode | None = None

        for node in tree.nodes():
            label = node.label
            if node.scrollable and scroll_node is None:
                scroll_node = node
            if node.editable:
                inputs.append(node)
                continue
            if not label:
                continue
            if node.clickable or node.long_clickable or node.tap_bounds() is not None:
                if self._status.match(label):
                    readable.append(label)
                elif node.is_control:
                    controls.append(node)
                else:
                    opens.append(node)
                    if len(label) > 40:
                        readable.append(label)
            else:
                readable.append(label)

        actions: list[Action] = []
        for index, node in enumerate(inputs):
            verb = "type" if index == 0 else f"type{index + 1}"
            hint = "password" if node.password else (node.label or "empty")
            actions.append(Action(0, verb, f"{verb} <text>  ({hint})", "input", node))

        submit = next((node for node in controls if self._submit.match(node.label)), None)
        if submit is not None and inputs:
            actions.append(Action(0, "send", "send", "submit", submit))

        if scroll_node is not None:
            actions.extend(
                (
                    Action(0, "up", "up", "nav"),
                    Action(0, "down", "down", "nav"),
                    Action(0, "left", "left", "nav"),
                    Action(0, "right", "right", "nav"),
                    Action(0, "scroll_up", "scroll_up", "scroll", scroll_node),
                    Action(0, "scroll_down", "scroll_down", "scroll", scroll_node),
                )
            )
        actions.extend((Action(0, "back", "back", "nav"), Action(0, "home", "home", "nav")))
        actions.extend(knowledge_actions)

        knowledge_labels = {
            action.node.label.casefold()
            for action in knowledge_actions
            if action.node is not None and action.node.label
        }
        seen: set[str] = set()
        unique_opens: list[UINode] = []
        open_candidates = [node for node in controls if node is not submit]
        open_candidates.extend(opens)
        for node in open_candidates:
            key = node.label.casefold()
            if key and key not in knowledge_labels and key not in seen:
                seen.add(key)
                unique_opens.append(node)

        total_pages = max(1, (len(unique_opens) + self.page_size - 1) // self.page_size)
        page = min(max(1, page), total_pages)
        visible_count = min(page * self.page_size, len(unique_opens))
        first_batch = unique_opens[: self.page_size]
        newly_revealed = unique_opens[self.page_size : visible_count]
        actions.extend(
            Action(0, "open", f"open: {node.label[:48]}", "open", node)
            for node in first_batch
        )
        if total_pages > 1:
            actions.append(
                Action(0, "more", f"more  (page {page + 1}/{total_pages})", "more")
            )
        actions.extend(
            Action(0, "open", f"open: {node.label[:48]}", "open", node)
            for node in newly_revealed
        )

        numbered = [
            Action(index, action.verb, action.label, action.kind, action.node, action.action_id)
            for index, action in enumerate(actions, start=1)
        ]
        clean_read = []
        for value in readable:
            if value not in clean_read and value.strip():
                clean_read.append(value.strip())
        return Frame(app, screen, clean_read[: self.read_cap], numbered, page, total_pages)
