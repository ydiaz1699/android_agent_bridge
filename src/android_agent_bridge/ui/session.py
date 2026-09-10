"""Stateful read-act-read session used by CLI and service adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.actions import KnowledgeActionError
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
        signature = f"{snapshot.package}:{screen}:{tuple((node.resource_id, node.text, node.content_desc) for node in snapshot.tree.nodes())}"
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
            knowledge_actions=self._knowledge_actions(pack, snapshot.tree, screen),
        )

    def do(self, identifier: str | int, text: str | None = None) -> UIResult:
        current = self.frame(preserve_page=True)
        action = self._find_action(current, identifier)
        if action is None:
            return UIResult(error=f"no action {identifier!r}", frame=current)
        if action.kind == "more":
            if current.total_pages <= self._page:
                return UIResult(error="no more pages", frame=current)
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
        if action.kind == "knowledge":
            return self._do_knowledge_action(current, action, text)
        if action.kind == "open":
            self._tap(action)
            return UIResult(did=f"opened {action.label.removeprefix('open: ')}", frame=self.frame())
        if action.kind == "nav":
            key = {
                "up": "KEYCODE_DPAD_UP",
                "down": "KEYCODE_DPAD_DOWN",
                "left": "KEYCODE_DPAD_LEFT",
                "right": "KEYCODE_DPAD_RIGHT",
                "back": "KEYCODE_BACK",
                "home": "KEYCODE_HOME",
            }.get(action.verb)
            if key is None:
                return UIResult(error=f"unsupported navigation: {action.verb}", frame=current)
            self.device.transport.keyevent(key)
            return UIResult(did=action.verb, frame=self.frame())
        if action.kind == "scroll":
            self._scroll(action)
            return UIResult(did=action.verb, frame=self.frame())
        return UIResult(error=f"unsupported action kind: {action.kind}", frame=current)

    def _knowledge_actions(self, pack: KnowledgePack | None, tree, screen: str) -> list[Action]:
        if pack is None or screen == "unknown":
            return []
        actions: list[Action] = []
        for spec in pack.action_specs.values():
            if spec.from_screen != screen:
                continue
            if spec.parameters:
                label = f"{spec.identifier} <{', '.join(sorted(spec.parameters))}>"
                actions.append(Action(0, spec.identifier, label, "knowledge", action_id=spec.identifier))
                continue
            try:
                node = spec.resolve(tree)
            except KnowledgeActionError:
                continue
            label = f"{spec.identifier} ({node.label})"
            actions.append(Action(0, spec.identifier, label, "knowledge", node, spec.identifier))
        return actions

    def _do_knowledge_action(self, current: Frame, action: Action, text: str | None) -> UIResult:
        if action.action_id is None:
            return UIResult(error="knowledge action has no identifier", frame=current)
        pack = self._resolve_pack(current.app)
        if pack is None:
            return UIResult(error="knowledge pack not found", frame=current)
        spec = pack.action_specs.get(action.action_id)
        if spec is None:
            return UIResult(error=f"unknown knowledge action: {action.action_id}", frame=current)
        try:
            if spec.parameters:
                if not text:
                    return UIResult(error="knowledge action requires text", frame=current)
                snapshot = self.device.snapshot()
                live_pack = self._resolve_pack(snapshot.package)
                live_screen = live_pack.matches_screen(snapshot.tree) if live_pack else "unknown"
                if live_pack is None or live_pack.identifier != pack.identifier:
                    return UIResult(error="state_mismatch: application changed", frame=current)
                if live_screen != spec.from_screen:
                    return UIResult(error=f"state_mismatch: expected {spec.from_screen}", frame=current)
                params = {name: text for name in spec.parameters}
                node = spec.resolve(snapshot.tree, params=params)
                self.device.tap_node(node)
            else:
                self._tap(action)
        except KnowledgeActionError as exc:
            return UIResult(error=f"{exc.code}: {exc}", frame=current)
        except ValueError as exc:
            return UIResult(error=f"action_failed: {exc}", frame=current)
        return UIResult(did=action.action_id, frame=self.frame())

    def _scroll(self, action: Action) -> None:
        if action.node is None or action.node.bounds is None:
            raise ValueError("scroll action has no viewport")
        bounds = action.node.bounds
        x = bounds.center_x
        top = bounds.top + max(1, int(bounds.bottom - bounds.top) // 5)
        bottom = bounds.bottom - max(1, int(bounds.bottom - bounds.top) // 5)
        if action.verb == "scroll_up":
            self.device.transport.swipe(x, bottom, x, top)
        elif action.verb == "scroll_down":
            self.device.transport.swipe(x, top, x, bottom)
        else:
            raise ValueError(f"unsupported scroll action: {action.verb}")

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
