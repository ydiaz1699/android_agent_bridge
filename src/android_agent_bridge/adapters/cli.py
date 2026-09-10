"""Small CLI adapter for the common bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from android_agent_bridge.adb.transport import ADBError, SubprocessADB
from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.registry import KnowledgeRegistry
from android_agent_bridge.ui.frame import FrameBuilder
from android_agent_bridge.ui.parser import parse_ui_xml


def _default_knowledge_root() -> Path:
    candidates = [
        Path.cwd() / "knowledge" / "apps",
        Path(__file__).resolve().parents[4] / "knowledge" / "apps",
    ]
    return next((path for path in candidates if path.is_dir()), candidates[0])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="android-agent", description="Agent-first Android ADB bridge")
    parser.add_argument("--serial", help="ADB device serial")
    parser.add_argument("--knowledge-root", type=Path, default=_default_knowledge_root())
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="show ADB and device information")
    doctor.set_defaults(handler=_doctor)

    frame = commands.add_parser("frame", help="read a UI dump as an agent frame")
    frame.add_argument("--xml", type=Path, help="read a local uiautomator XML instead of ADB")
    frame.add_argument("--package", default="unknown", help="package name for a local XML")
    frame.set_defaults(handler=_frame)

    knowledge = commands.add_parser("knowledge", help="inspect application knowledge packs")
    knowledge_commands = knowledge.add_subparsers(dest="knowledge_command", required=True)
    resolve = knowledge_commands.add_parser("resolve", help="resolve package or alias")
    resolve.add_argument("value")
    resolve.set_defaults(handler=_resolve_knowledge)
    return parser


def _registry(args: argparse.Namespace) -> KnowledgeRegistry:
    return KnowledgeRegistry(args.knowledge_root)


def _doctor(args: argparse.Namespace) -> int:
    adb = SubprocessADB(args.serial)
    try:
        devices = adb.devices()
        package, activity = AndroidDevice(adb).foreground() if devices else ("unknown", "unknown")
        print(json.dumps({"devices": devices, "foreground": {"package": package, "activity": activity}}))
    except ADBError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    return 0


def _frame(args: argparse.Namespace) -> int:
    registry = _registry(args)
    if args.xml:
        xml = args.xml.read_text(encoding="utf-8")
        tree = parse_ui_xml(xml)
        pack = registry.resolve(args.package)
        screen = pack.matches_screen(tree) if pack else "unknown"
        frame = FrameBuilder().build(
            tree,
            app=pack.identifier if pack else args.package,
            screen=screen,
        )
    else:
        device = AndroidDevice(SubprocessADB(args.serial))
        snapshot = device.snapshot()
        pack = registry.resolve(snapshot.package)
        screen = pack.matches_screen(snapshot.tree) if pack else "unknown"
        frame = FrameBuilder().build(snapshot.tree, app=pack.identifier if pack else snapshot.package, screen=screen)
    print(json.dumps(frame.to_dict(), ensure_ascii=False))
    return 0


def _resolve_knowledge(args: argparse.Namespace) -> int:
    pack = _registry(args).resolve(args.value)
    if pack is None:
        print(json.dumps({"found": False, "value": args.value}))
        return 1
    print(json.dumps({"found": True, "id": pack.identifier, "manifest": pack.manifest}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
