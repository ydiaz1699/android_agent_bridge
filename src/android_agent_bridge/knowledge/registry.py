"""Load and match application knowledge packs on demand."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from android_agent_bridge.ui.parser import UITree
from android_agent_bridge.ui.selectors import SelectorError, SelectorResolver

from .actions import KnowledgeActionSpec, compile_actions


@dataclass(frozen=True, slots=True)
class KnowledgePack:
    """Declarative application knowledge, kept separate from the UI engine."""

    root: Path
    manifest: dict[str, Any]
    selectors: dict[str, Any]
    states: dict[str, Any]
    actions: dict[str, Any]

    @property
    def identifier(self) -> str:
        return str(self.manifest.get("id", self.root.name))

    @property
    def package_names(self) -> list[str]:
        return [str(value) for value in self.manifest.get("package_names", [])]

    @property
    def action_specs(self) -> dict[str, KnowledgeActionSpec]:
        return compile_actions(self.actions)

    def matches_screen(self, tree: UITree) -> str:
        """Return the first state whose declarative indicators match the tree."""
        resolver = SelectorResolver()
        for state_name, definition in self.states.items():
            indicators = definition.get("indicators", [])
            if not indicators:
                continue
            try:
                if all(resolver.resolve(tree, indicator) for indicator in indicators):
                    return state_name
            except SelectorError:
                continue
        return "unknown"


class KnowledgeRegistry:
    """Discover packs by package name, alias or explicit pack identifier."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._cache: dict[str, KnowledgePack] = {}

    def identifiers(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(path.name for path in self.root.iterdir() if path.is_dir())

    def resolve(self, value: str) -> KnowledgePack | None:
        normalized = value.casefold()
        for identifier in self.identifiers():
            pack = self.load(identifier)
            aliases = [str(alias).casefold() for alias in pack.manifest.get("aliases", [])]
            if normalized in {pack.identifier.casefold(), *aliases, *(name.casefold() for name in pack.package_names)}:
                return pack
        return None

    def load(self, identifier: str) -> KnowledgePack:
        if identifier in self._cache:
            return self._cache[identifier]
        pack_root = self.root / identifier
        if not pack_root.is_dir():
            raise FileNotFoundError(f"Knowledge pack not found: {identifier}")
        pack = KnowledgePack(
            root=pack_root,
            manifest=_read_json(pack_root / "manifest.json"),
            selectors=_read_json(pack_root / "selectors.json"),
            states=_read_json(pack_root / "states.json"),
            actions=_read_json(pack_root / "actions.json"),
        )
        self._cache[identifier] = pack
        return pack


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise TypeError(f"Knowledge file must contain an object: {path}")
    return value
