"""Generic Android device facade."""

from __future__ import annotations

import re
from dataclasses import dataclass

from android_agent_bridge.adb.transport import ADBTransport
from android_agent_bridge.ui.parser import UINode, UITree, parse_ui_xml


@dataclass(slots=True)
class AndroidSnapshot:
    """One fresh observation of the device UI."""

    tree: UITree
    package: str
    activity: str


class AndroidDevice:
    """Device-level operations shared by phones, emulators and Android TVs."""

    def __init__(self, transport: ADBTransport) -> None:
        self.transport = transport

    def foreground(self) -> tuple[str, str]:
        output = self.transport.shell(("dumpsys", "window"))
        match = re.search(r"mCurrentFocus=Window\{[^ ]+ \w+ ([^/]+)/([^}]+)", output)
        if not match:
            return "unknown", "unknown"
        return match.group(1), match.group(2)

    def snapshot(
        self,
        xml: str | None = None,
        *,
        package: str | None = None,
        activity: str | None = None,
    ) -> AndroidSnapshot:
        source = xml if xml is not None else self.transport.dump_ui()
        if package is None or activity is None:
            current_package, current_activity = self.foreground()
            package = package or current_package
            activity = activity or current_activity
        return AndroidSnapshot(parse_ui_xml(source), package, activity)

    def tap_node(self, node: UINode) -> None:
        bounds = node.tap_bounds()
        if bounds is None:
            raise ValueError(f"Node has no tappable bounds: {node.label!r}")
        self.transport.tap(bounds.center_x, bounds.center_y)
