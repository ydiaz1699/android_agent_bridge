from __future__ import annotations

from pathlib import Path

from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.registry import KnowledgeRegistry
from android_agent_bridge.ui.session import UISession

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge" / "apps"
HOME_XML = (ROOT / "examples" / "mgandroid_home.xml").read_text(encoding="utf-8")
LIVE_XML = (ROOT / "examples" / "mgandroid_live.xml").read_text(encoding="utf-8")
VOD_XML = (ROOT / "examples" / "mgandroid_vod.xml").read_text(encoding="utf-8")


class NavigationTransport:
    def __init__(self) -> None:
        self.xml = HOME_XML
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
            return "mCurrentFocus=Window{abc u0 com.android.mgandroid/.MainActivity}"
        if args[:3] == ("cmd", "package", "query-activities"):
            return "com.android.mgandroid/.MainActivity\n"
        return ""

    def dump_ui(self, *, timeout: float = 30.0) -> str:
        self.calls.append(("dump_ui", ()))
        return self.xml

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", (str(x), str(y))))
        self.xml = LIVE_XML if x >= 500 else VOD_XML

    def keyevent(self, key: str) -> None:
        self.calls.append(("keyevent", (key,)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.calls.append(("swipe", (str(x1), str(y1), str(x2), str(y2), str(duration_ms))))

    def input_text(self, text: str) -> None:
        self.calls.append(("input_text", (text,)))


def test_open_live_verifies_live_destination_from_fresh_frame() -> None:
    transport = NavigationTransport()
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    result = session.do("open_live")

    assert result.did == "open_live"
    assert result.error is None
    assert result.frame is not None
    assert result.frame.screen == "live"
    assert transport.calls.count(("dump_ui", ())) == 2


def test_open_movies_verifies_generic_vod_destination() -> None:
    transport = NavigationTransport()
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    result = session.do("open_movies")

    assert result.did == "open_movies"
    assert result.frame is not None
    assert result.frame.screen == "vod"
    assert any("Contenido de ejemplo" in action.label for action in result.frame.actions)


def test_navigation_returns_verification_error_when_destination_is_not_recognized() -> None:
    transport = NavigationTransport()
    transport.xml = HOME_XML
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    transport.tap = lambda x, y: transport.calls.append(("tap", (str(x), str(y))))
    result = session.do("open_live")

    assert result.did is None
    assert result.error_code == "verification_failed"
    assert result.frame is not None
    assert result.frame.screen == "home"
