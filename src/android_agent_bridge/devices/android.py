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

    def list_apps(self) -> list[dict[str, str]]:
        """List launchable packages without exposing raw shell output."""
        output = self.transport.shell(
            (
                "cmd",
                "package",
                "query-activities",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
            )
        )
        packages = sorted(
            {
                match.group(1)
                for line in output.splitlines()
                if (match := re.match(r"^\s*([a-zA-Z][\w.]*)/", line))
            }
        )
        return [
            {"name": package.rsplit(".", 1)[-1], "package": package}
            for package in packages
        ]

    def resolve_package(self, name: str) -> str | None:
        """Resolve an alias or installed package without invoking a shell."""
        value = name.strip()
        if not value:
            return None
        aliases = {
            "settings": "com.android.settings",
            "chrome": "com.android.chrome",
            "browser": "com.android.chrome",
            "gmail": "com.google.android.gm",
            "whatsapp": "com.whatsapp",
            "contacts": "com.google.android.contacts",
            "youtube": "com.google.android.youtube",
            "camera": "com.android.camera2",
            "mgandroid": "com.android.mgandroid",
            "mg android": "com.android.mgandroid",
        }
        candidate = aliases.get(value.casefold(), value)
        apps = self.list_apps()
        installed = {app["package"] for app in apps}
        if re.fullmatch(r"[a-zA-Z][\w]*(?:\.[\w]+)+", candidate):
            return candidate if candidate in installed else None
        token = re.sub(r"\s+", "", value.casefold())
        for package in sorted(installed):
            if package.rsplit(".", 1)[-1].casefold() == token or token in package.casefold():
                return package
        return None

    def open_app(self, name: str, *, fresh: bool = False) -> dict[str, str | bool]:
        """Open an installed launchable app, optionally from a clean start."""
        package = self.resolve_package(name)
        if package is None:
            raise ValueError(f"No installed launchable app matches: {name}")
        if fresh:
            self.transport.shell(("am", "force-stop", package))
            self.transport.keyevent("KEYCODE_HOME")
        output = self.transport.shell(
            ("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        )
        if "No activities found" in output or "aborted" in output.casefold():
            raise RuntimeError(f"App has no launchable activity: {package}")
        return {"name": name, "package": package, "fresh": fresh}

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
