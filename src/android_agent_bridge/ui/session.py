"""Stateful read-act-read session used by CLI and service adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.registry import KnowledgePack, KnowledgeRegistry

from .frame import Action, Frame, FrameBuilder


@dataclass(slots=True)
class UIResult:
    """Structured result returned after an action."""

    did: str | None = None
    error: str | None = None
    frame: Frame | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.did is not None:
            result["did"] = self.did
        if self.error is not None:
            result["error"] = self.error
        if self.frame is not None:
            result["frame"] = self.frame.to_dict()
        return result


class UISession:
    """Build fresh frames and execute actions against one Android device."""

    def __init__(
        self,
        device: AndroidDevice,
        registry: KnowledgeRegistry | None = None,
        *,
        frame_builder: FrameBuilder | None = None,
    ) -> None:
        self.device = device
        self.registry = registry
        self.frame_builder = frame_builder or FrameBuilder()
        self._page = 1
        self._signature = ""

    def frame(self, *, page: int | None = None, xml: str | None = None, preserve_page: bool = False) -> Frame:
        snapshot = self.device.snapshot(xml)
        pack = self._resolve_pack(snapshot.package)
        screen = pack.matches_screen(snapshot.tree) if pack else "unknown"
        signature = f"{snapshot.package}:{screen}:{len(snapshot.tree.nodes())}"
        if signature != self._signature:
            self._signature = signature
            self._page = 1
        if not preserve_page:
            self._page = 1
        if page is not None:
            self._page = page
        return self.frame_builder.build(
            snapshot.tree,
            app=pack.identifier if pack else snapshot.package,
            screen=screen,
            page=self._page,
        )

    def do(self, identifier: str | int, text: str | None = None) -> UIResult:
        current = self.frame(preserve_page=True)
        action = self._find_action(current, identifier)
        if action is None:
            return UIResult(error=f"no action {identifier!r}", frame=current)
        if action.kind == "more":
            self._page += 1
            return UIResult(did=f"more (page {self._page})", frame=self.frame(preserve_page=True))
        if action.kind == "input":
            if not text:
                return UIResult(error="input action requires text", frame=current)
            self._tap(action)
            self.device.transport.input_text(text)
            return UIResult(did=f"typed {text!r}", frame=self.frame())
        if action.kind == "submit":
            self._tap(action)
            return UIResult(did="submitted", frame=self.frame())
        if action.kind == "open":
            self._tap(action)
            return UIResult(did=f"opened {action.label.removeprefix('open: ')}", frame=self.frame())
        if action.kind == "nav":
            if action.verb == "up":
                self.device.transport.swipe(540, 600, 540, 1600)
            elif action.verb == "down":
                self.device.transport.swipe(540, 1600, 540, 600)
            else:
                self.device.transport.keyevent("KEYCODE_HOME" if action.verb == "home" else "KEYCODE_BACK")
            return UIResult(did=action.verb, frame=self.frame())
        return UIResult(error=f"unsupported action kind: {action.kind}", frame=current)

    def _resolve_pack(self, package: str) -> KnowledgePack | None:
        return self.registry.resolve(package) if self.registry else None

    def _find_action(self, frame: Frame, identifier: str | int) -> Action | None:
        value = str(identifier).strip().casefold()
        if value.isdecimal():
            number = int(value)
            return next((action for action in frame.actions if action.number == number), None)
        return next((action for action in frame.actions if action.verb.casefold() == value), None)

    def _tap(self, action: Action) -> None:
        if action.node is None:
            raise ValueError(f"Action has no target: {action.label}")
        self.device.tap_node(action.node)
