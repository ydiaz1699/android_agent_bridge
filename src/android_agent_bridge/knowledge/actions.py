"""Validated and executable knowledge-pack actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from android_agent_bridge.ui.parser import UINode, UITree
from android_agent_bridge.ui.selectors import SelectorError, SelectorResolver


class KnowledgeActionError(ValueError):
    """Base error for an invalid or unexecutable pack action."""

    code = "knowledge_action_error"


class InvalidKnowledgeAction(KnowledgeActionError):
    """The action schema is invalid or contains unsafe fields."""

    code = "invalid_knowledge_action"


class KnowledgeStateMismatch(KnowledgeActionError):
    """The action was requested from a state different from its declaration."""

    code = "state_mismatch"


@dataclass(frozen=True, slots=True)
class KnowledgeActionSpec:
    """One validated, declarative action from a knowledge pack."""

    identifier: str
    from_screen: str
    intent: str
    strategies: tuple[dict[str, Any], ...]

    @property
    def parameters(self) -> frozenset[str]:
        values: set[str] = set()
        for strategy in self.strategies:
            for value in strategy.values():
                if isinstance(value, str):
                    values.update(match.group(1) for match in re.finditer(r"\$([A-Za-z_]\w*)", value))
        return frozenset(values)

    def resolve(
        self,
        tree: UITree,
        *,
        params: dict[str, Any] | None = None,
        resolver: SelectorResolver | None = None,
    ) -> UINode:
        resolver = resolver or SelectorResolver()
        missing = self.parameters - set(params or {})
        if missing:
            names = ", ".join(sorted(missing))
            raise InvalidKnowledgeAction(f"Missing action parameters: {names}")
        last_error: SelectorError | None = None
        for strategy in self.strategies:
            try:
                return resolver.resolve(tree, strategy, params=params)
            except SelectorError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise InvalidKnowledgeAction(f"Action has no strategies: {self.identifier}")


def compile_actions(raw: dict[str, Any]) -> dict[str, KnowledgeActionSpec]:
    """Validate pack actions and return typed specs.

    Only semantic intents are accepted. Shell commands, coordinates and
    arbitrary executable fields are rejected rather than ignored.
    """
    if not isinstance(raw, dict):
        raise InvalidKnowledgeAction("actions.json must contain an object")
    compiled: dict[str, KnowledgeActionSpec] = {}
    allowed_intents = {"navigate", "select_by_name"}
    for identifier, definition in raw.items():
        if not isinstance(identifier, str) or not identifier.strip():
            raise InvalidKnowledgeAction("Action identifiers must be non-empty strings")
        if not isinstance(definition, dict):
            raise InvalidKnowledgeAction(f"Action must be an object: {identifier}")
        from_screen = definition.get("from")
        intent = definition.get("intent")
        strategies = definition.get("strategies")
        if not isinstance(from_screen, str) or not from_screen:
            raise InvalidKnowledgeAction(f"Action has invalid from state: {identifier}")
        if intent not in allowed_intents:
            raise InvalidKnowledgeAction(f"Unsupported intent for {identifier}: {intent!r}")
        if not isinstance(strategies, list) or not strategies:
            raise InvalidKnowledgeAction(f"Action has no strategies: {identifier}")
        normalized: list[dict[str, Any]] = []
        for strategy in strategies:
            if not isinstance(strategy, dict):
                raise InvalidKnowledgeAction(f"Strategy must be an object: {identifier}")
            # SelectorResolver performs the definitive field validation. Run it
            # against an empty tree only for schema field validation below.
            unknown = set(strategy) - SelectorResolver._supported
            if unknown:
                fields = ", ".join(sorted(str(value) for value in unknown))
                raise InvalidKnowledgeAction(f"Unsupported strategy fields in {identifier}: {fields}")
            normalized.append(dict(strategy))
        compiled[identifier] = KnowledgeActionSpec(
            identifier=identifier,
            from_screen=from_screen,
            intent=intent,
            strategies=tuple(normalized),
        )
    return compiled
