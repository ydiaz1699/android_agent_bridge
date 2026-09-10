from __future__ import annotations

from pathlib import Path

import pytest

from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.registry import KnowledgeRegistry
from android_agent_bridge.ui.session import UISession
from android_agent_bridge.workflows.mgandroid import LifecycleError, MGAndroidLifecycle

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge" / "apps"
HOME_XML = (ROOT / "examples" / "mgandroid_home.xml").read_text(encoding="utf-8")
LIVE_XML = (ROOT / "examples" / "mgandroid_live.xml").read_text(encoding="utf-8")
UNKNOWN_XML = (ROOT / "examples" / "unknown_screen.xml").read_text(encoding="utf-8")


class LifecycleTransport:
    def __init__(
        self,
        *,
        xml: str = HOME_XML,
        package: str = "com.android.mgandroid",
        xml_sequence: list[str] | None = None,
    ) -> None:
        self.xml = xml
        self.package = package
        self.xml_sequence = list(xml_sequence or [])
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def run(self, args, *, timeout: float = 30.0) -> str:
        args = tuple(str(value) for value in args)
        self.calls.append(("run", args))
        if args == ("devices",):
            return "List of devices attached\nserial-1\tdevice\n"
        return ""

    def shell(self, args, *, timeout: float = 30.0) -> str:
        args = tuple(str(value) for value in args)
        self.calls.append(("shell", args))
        if args == ("dumpsys", "window"):
            return f"mCurrentFocus=Window{{abc u0 {self.package}/.MainActivity}}"
        if args[:3] == ("cmd", "package", "query-activities"):
            return "com.android.mgandroid/.MainActivity\ncom.android.settings/.Settings\n"
        if args[:2] == ("monkey", "-p"):
            self.package = "com.android.mgandroid"
            self.xml = HOME_XML
            return "Events injected: 1"
        return ""

    def dump_ui(self, *, timeout: float = 30.0) -> str:
        self.calls.append(("dump_ui", ()))
        if self.xml_sequence:
            self.xml = self.xml_sequence.pop(0)
        return self.xml

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", (str(x), str(y))))

    def keyevent(self, key: str) -> None:
        self.calls.append(("keyevent", (key,)))
        if key == "KEYCODE_DPAD_UP":
            self.xml = HOME_XML
        if key == "KEYCODE_BACK" and self.xml in {LIVE_XML, UNKNOWN_XML}:
            self.xml = HOME_XML

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.calls.append(("swipe", (str(x1), str(y1), str(x2), str(y2), str(duration_ms))))

    def input_text(self, text: str) -> None:
        self.calls.append(("input_text", (text,)))


def lifecycle(transport: LifecycleTransport, *, session: UISession | None = None) -> MGAndroidLifecycle:
    device = AndroidDevice(transport)
    registry = KnowledgeRegistry(KNOWLEDGE)
    pack = registry.resolve("mgandroid")
    assert pack is not None
    return MGAndroidLifecycle(
        device,
        pack,
        session=session,
        sleeper=lambda _: None,
        default_timeout=0.1,
        default_interval=0,
    )


def test_wait_ready_retries_until_pack_recognizes_home() -> None:
    transport = LifecycleTransport(xml_sequence=[LIVE_XML, HOME_XML])
    result = lifecycle(transport).wait_ready(timeout=0.1, interval=0)

    assert result.package == "com.android.mgandroid"
    assert result.screen == "home"
    assert transport.calls.count(("dump_ui", ())) == 2


def test_wait_ready_times_out_without_claiming_unknown_screen_is_ready() -> None:
    transport = LifecycleTransport(xml=UNKNOWN_XML)

    with pytest.raises(LifecycleError) as caught:
        lifecycle(transport).wait_ready(timeout=0)

    assert caught.value.code == "lifecycle_timeout"
    assert "unknown" in str(caught.value)


def test_ensure_home_is_idempotent_and_does_not_press_back_on_home() -> None:
    transport = LifecycleTransport(xml=HOME_XML)
    result = lifecycle(transport).ensure_home(timeout=0)

    assert result.screen == "home"
    assert ("keyevent", ("KEYCODE_BACK",)) not in transport.calls
    assert not any(args[:2] == ("monkey", "-p") for kind, args in transport.calls if kind == "shell")


def test_ensure_home_uses_bounded_back_before_restart() -> None:
    transport = LifecycleTransport(xml=LIVE_XML)
    result = lifecycle(transport).ensure_home(timeout=0.1, interval=0, max_back=1)

    assert result.screen == "home"
    assert transport.calls.count(("keyevent", ("KEYCODE_BACK",))) == 1
    assert not any(args[:2] == ("monkey", "-p") for kind, args in transport.calls if kind == "shell")


def test_foreign_foreground_is_not_navigated_with_back() -> None:
    transport = LifecycleTransport(xml=HOME_XML, package="com.android.settings")
    result = lifecycle(transport).ensure_home(timeout=0.1, interval=0)

    assert result.screen == "home"
    assert ("keyevent", ("KEYCODE_BACK",)) not in transport.calls
    assert ("shell", ("am", "force-stop", "com.android.mgandroid")) in transport.calls
    assert any(args[:2] == ("monkey", "-p") for kind, args in transport.calls if kind == "shell")


def test_restart_and_close_reset_persistent_ui_session_state() -> None:
    transport = LifecycleTransport(xml_sequence=[HOME_XML])
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))
    session._page = 4
    session._signature = "stale"
    mg = lifecycle(transport, session=session)

    restarted = mg.restart(timeout=0.1, interval=0)
    assert restarted.screen == "home"
    assert session._page == 1
    assert session._signature == ""
    assert transport.calls.count(("shell", ("am", "force-stop", "com.android.mgandroid"))) == 1

    session._page = 3
    session._signature = "stale-again"
    mg.close()
    assert session._page == 1
    assert session._signature == ""
    assert transport.calls.count(("shell", ("am", "force-stop", "com.android.mgandroid"))) == 2
    assert transport.calls.count(("dump_ui", ())) == 1
