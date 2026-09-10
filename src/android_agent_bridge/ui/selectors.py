"""Deterministic, declarative selectors for knowledge packs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar

from .parser import Bounds, UINode, UITree


class SelectorError(ValueError):
    """Base error for a selector that cannot be resolved."""

    code = "selector_error"


class SelectorNotFound(SelectorError):
    """No node matched the selector."""

    code = "selector_not_found"


class UnsupportedSelector(SelectorError):
    """The selector contains an unsupported or unsafe field."""

    code = "unsupported_selector"


class MissingSelectorParameter(SelectorError):
    """A selector references a parameter that was not supplied."""

    code = "selector_parameter_missing"


class SelectorResolver:
    """Resolve pack selectors against one fresh UI tree.

    The resolver never stores nodes or bounds. Callers may retain the returned
    node only for the duration of the current read-act-read operation.
    """

    _supported: ClassVar[set[str]] = {
        "resource_id",
        "text",
        "text_contains",
        "text_regex",
        "content_desc",
        "content_desc_contains",
        "content_desc_regex",
        "class_name",
        "class",
        "parent_clickable",
        "region",
    }

    def resolve(
        self,
        tree: UITree,
        selector: Mapping[str, Any],
        *,
        params: Mapping[str, Any] | None = None,
    ) -> UINode:
        matches = self.resolve_all(tree, selector, params=params)
        if not matches:
            raise SelectorNotFound(f"No UI node matches selector: {dict(selector)!r}")
        return matches[0]

    def resolve_all(
        self,
        tree: UITree,
        selector: Mapping[str, Any],
        *,
        params: Mapping[str, Any] | None = None,
    ) -> list[UINode]:
        if not isinstance(selector, Mapping) or not selector:
            raise UnsupportedSelector("Selector must be a non-empty object")
        unknown = set(selector) - self._supported
        if unknown:
            fields = ", ".join(sorted(str(value) for value in unknown))
            raise UnsupportedSelector(f"Unsupported selector fields: {fields}")
        resolved = {key: self._value(value, params) for key, value in selector.items()}
        return [node for node in tree.nodes() if self._matches(node, resolved)]

    @staticmethod
    def _value(value: Any, params: Mapping[str, Any] | None) -> Any:
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        key = value[1:]
        if not params or key not in params or params[key] is None:
            raise MissingSelectorParameter(f"Missing selector parameter: {key}")
        return str(params[key])

    def _matches(self, node: UINode, selector: Mapping[str, Any]) -> bool:
        for key, expected in selector.items():
            if key == "resource_id" and not self._resource_id_matches(node.resource_id, str(expected)):
                return False
            if key == "text" and node.text != str(expected):
                return False
            if key == "text_contains" and str(expected).casefold() not in node.text.casefold():
                return False
            if key == "text_regex" and re.search(str(expected), node.text) is None:
                return False
            if key == "content_desc" and node.content_desc != str(expected):
                return False
            if key == "content_desc_contains" and str(expected).casefold() not in node.content_desc.casefold():
                return False
            if key == "content_desc_regex" and re.search(str(expected), node.content_desc) is None:
                return False
            if key in {"class_name", "class"} and node.class_name != str(expected):
                return False
            if key == "parent_clickable" and bool(expected) and not any(
                ancestor.clickable or ancestor.long_clickable for ancestor in node.ancestors()
            ):
                return False
            if key == "region" and not self._in_region(node.bounds, expected):
                return False
        return True

    @staticmethod
    def _resource_id_matches(actual: str, expected: str) -> bool:
        if actual == expected:
            return True
        if not actual or not expected:
            return False
        # Android dumps commonly use package:id/name while packs may use name.
        return actual.rsplit("/", 1)[-1] == expected.rsplit("/", 1)[-1]

    @staticmethod
    def _in_region(bounds: Bounds | None, region: Any) -> bool:
        if bounds is None or not isinstance(region, Mapping):
            return False
        try:
            left = int(region["left"])
            top = int(region["top"])
            right = int(region["right"])
            bottom = int(region["bottom"])
        except (KeyError, TypeError, ValueError):
            raise UnsupportedSelector("region must contain integer left/top/right/bottom") from None
        return left <= bounds.center_x <= right and top <= bounds.center_y <= bottom
