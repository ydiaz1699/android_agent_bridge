"""Parse Android UI Automator XML into a navigable tree."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True, slots=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2


@dataclass(slots=True)
class UINode:
    """A UI node with parent/child links and normalized Android attributes."""

    text: str = ""
    content_desc: str = ""
    resource_id: str = ""
    class_name: str = ""
    clickable: bool = False
    long_clickable: bool = False
    scrollable: bool = False
    editable: bool = False
    password: bool = False
    bounds: Bounds | None = None
    parent: UINode | None = None
    children: list[UINode] = field(default_factory=list)

    @property
    def label(self) -> str:
        return (self.text or self.content_desc).strip()

    @property
    def is_control(self) -> bool:
        return (
            (not self.text and bool(self.content_desc))
            or self.class_name.rsplit(".", 1)[-1] in {"Button", "ImageButton", "ImageView"}
        )

    def tap_bounds(self) -> Bounds | None:
        """Return the current node or nearest clickable ancestor target."""
        node: UINode | None = self
        while node is not None:
            if node.clickable or node.long_clickable:
                return node.bounds
            node = node.parent
        # EditText widgets are focusable even when Android does not mark them
        # clickable in the dump, so their own bounds remain a valid input target.
        return self.bounds if self.editable else None

    def ancestors(self) -> Iterable[UINode]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


@dataclass(slots=True)
class UITree:
    root: UINode

    def nodes(self) -> list[UINode]:
        result: list[UINode] = []

        def visit(node: UINode) -> None:
            result.append(node)
            for child in node.children:
                visit(child)

        visit(self.root)
        return result

    def find(self, *, text: str | None = None, resource_id: str | None = None) -> list[UINode]:
        return [
            node
            for node in self.nodes()
            if (text is None or node.text == text)
            and (resource_id is None or node.resource_id == resource_id)
        ]


def _bool(value: str | None) -> bool:
    return value == "true"


def _bounds(value: str | None) -> Bounds | None:
    if not value:
        return None
    match = _BOUNDS_RE.fullmatch(value)
    if not match:
        return None
    left, top, right, bottom = (int(part) for part in match.groups())
    return Bounds(left, top, right, bottom)


def _node(element: ET.Element, parent: UINode | None = None) -> UINode:
    attrs = element.attrib
    node = UINode(
        text=attrs.get("text", ""),
        content_desc=attrs.get("content-desc", ""),
        resource_id=attrs.get("resource-id", ""),
        class_name=attrs.get("class", ""),
        clickable=_bool(attrs.get("clickable")),
        long_clickable=_bool(attrs.get("long-clickable")),
        scrollable=_bool(attrs.get("scrollable")),
        editable=attrs.get("class", "").rsplit(".", 1)[-1] == "EditText" or _bool(attrs.get("password")),
        password=_bool(attrs.get("password")),
        bounds=_bounds(attrs.get("bounds")),
        parent=parent,
    )
    for child_element in element:
        if child_element.tag == "node":
            node.children.append(_node(child_element, node))
    return node


def parse_ui_xml(xml: str) -> UITree:
    """Parse a UI Automator dump, accepting either hierarchy or a node root."""
    try:
        root_element = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("Invalid UI Automator XML") from exc

    if root_element.tag == "hierarchy":
        first_node = next((child for child in root_element if child.tag == "node"), None)
        if first_node is None:
            raise ValueError("UI XML contains no root node")
        return UITree(_node(first_node))
    if root_element.tag == "node":
        return UITree(_node(root_element))
    raise ValueError(f"Unsupported UI XML root: {root_element.tag}")
