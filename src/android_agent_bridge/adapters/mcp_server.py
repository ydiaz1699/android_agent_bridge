"""Persistent MCP adapter for android_agent_bridge.

The MCP process owns one ADB transport and one UISession for its whole lifetime.
This is intentional: frame pagination and action resolution must not be reset by
spawning a new child process for every tool call.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from threading import RLock
from typing import Any

from android_agent_bridge.adb.transport import ADBError, SubprocessADB
from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.registry import KnowledgeRegistry
from android_agent_bridge.ui.session import UISession


def default_knowledge_root() -> Path:
    """Find the checkout knowledge directory, with an environment override."""
    configured = os.environ.get("ANDROID_AGENT_KNOWLEDGE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = (
        Path.cwd() / "knowledge" / "apps",
        Path(__file__).resolve().parents[3] / "knowledge" / "apps",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])


class BridgeRuntime:
    """Own the persistent device/session state used by MCP tools."""

    def __init__(self, *, serial: str | None, knowledge_root: Path) -> None:
        self.transport = SubprocessADB(serial=serial or os.environ.get("ANDROID_AGENT_SERIAL"))
        self.device = AndroidDevice(self.transport)
        self.registry = KnowledgeRegistry(knowledge_root)
        self.session = UISession(self.device, self.registry)
        self._lock = RLock()

    def doctor(self) -> dict[str, Any]:
        with self._lock:
            try:
                devices = self.transport.devices()
                result: dict[str, Any] = {"devices": devices}
                if devices:
                    package, activity = self.device.foreground()
                    result["foreground"] = {"package": package, "activity": activity}
                else:
                    result["foreground"] = None
                return result
            except ADBError as exc:
                return {"error": str(exc)}

    def app_list(self) -> dict[str, Any]:
        with self._lock:
            try:
                return {"apps": self.device.list_apps()}
            except (ADBError, RuntimeError) as exc:
                return {"error": str(exc)}

    def app_open(self, name: str, fresh: bool = False) -> dict[str, Any]:
        with self._lock:
            try:
                return {"opened": self.device.open_app(name, fresh=fresh)}
            except (ADBError, RuntimeError, ValueError) as exc:
                return {"error": str(exc)}

    def frame(self) -> dict[str, Any]:
        with self._lock:
            try:
                return self.session.frame().to_dict()
            except (ADBError, RuntimeError, ValueError) as exc:
                return {"error": str(exc)}

    def ui_do(self, action: str, text: str | None = None) -> dict[str, Any]:
        with self._lock:
            try:
                return self.session.do(action, text).to_dict()
            except (ADBError, RuntimeError, ValueError) as exc:
                return {"error": str(exc)}

    def knowledge_resolve(self, value: str) -> dict[str, Any]:
        with self._lock:
            pack = self.registry.resolve(value)
            if pack is None:
                return {"found": False, "value": value}
            return {
                "found": True,
                "id": pack.identifier,
                "version": pack.manifest.get("version"),
                "package_names": pack.package_names,
                "capabilities": pack.manifest.get("capabilities", []),
            }


def build_server(runtime: BridgeRuntime):
    """Build an MCP server bound to one persistent bridge runtime."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is optional. Install it with: pip install 'android-agent-bridge[mcp]'"
        ) from exc

    server = FastMCP("android-agent-bridge")

    @server.tool()
    def android_doctor() -> dict[str, Any]:
        """Check ADB devices and the foreground Android application."""
        return runtime.doctor()

    @server.tool()
    def android_app_list() -> dict[str, Any]:
        """List launchable applications on the connected Android device."""
        return runtime.app_list()

    @server.tool()
    def android_app_open(name: str, fresh: bool = False) -> dict[str, Any]:
        """Open an app by alias or package; use fresh to force a clean start."""
        return runtime.app_open(name, fresh)

    @server.tool()
    def android_ui_frame() -> dict[str, Any]:
        """Read the current screen as compact content and numbered actions."""
        return runtime.frame()

    @server.tool()
    def android_ui_do(action: str, text: str | None = None) -> dict[str, Any]:
        """Execute a frame action by number or stable verb and return the next frame."""
        return runtime.ui_do(action, text)

    @server.tool()
    def android_knowledge_resolve(value: str) -> dict[str, Any]:
        """Resolve an app package or alias to its compact knowledge-pack summary."""
        return runtime.knowledge_resolve(value)

    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MCP server for android_agent_bridge")
    parser.add_argument("--serial", help="ADB serial; otherwise ANDROID_AGENT_SERIAL is used")
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=default_knowledge_root(),
        help="Directory containing application knowledge packs",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        server = build_server(BridgeRuntime(serial=args.serial, knowledge_root=args.knowledge_root))
        server.run(transport="stdio")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
