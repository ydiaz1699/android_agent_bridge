from __future__ import annotations

from pathlib import Path

import pytest

from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.knowledge.actions import compile_actions
from android_agent_bridge.knowledge.registry import KnowledgeRegistry
from android_agent_bridge.ui.frame import FrameBuilder
from android_agent_bridge.ui.parser import parse_ui_xml
from android_agent_bridge.ui.selectors import SelectorNotFound, SelectorResolver
from android_agent_bridge.ui.session import UISession

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge" / "apps"
HOME_XML = (ROOT / "examples" / "mgandroid_home.xml").read_text(encoding="utf-8")


class FakeADBTransport:
    def __init__(self, xml: str = HOME_XML) -> None:
        self.xml = xml
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
            return "com.android.mgandroid/.MainActivity\ncom.android.settings/.Settings\n"
        if args[:2] == ("monkey", "-p"):
            return "Events injected: 1"
        return ""

    def dump_ui(self, *, timeout: float = 30.0) -> str:
        self.calls.append(("dump_ui", ()))
        return self.xml

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", (str(x), str(y))))

    def keyevent(self, key: str) -> None:
        self.calls.append(("keyevent", (key,)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.calls.append(("swipe", (str(x1), str(y1), str(x2), str(y2), str(duration_ms))))

    def input_text(self, text: str) -> None:
        self.calls.append(("input_text", (text,)))


def test_list_apps_and_package_resolution_use_real_regexes() -> None:
    transport = FakeADBTransport()
    device = AndroidDevice(transport)

    assert device.list_apps() == [
        {"name": "mgandroid", "package": "com.android.mgandroid"},
        {"name": "settings", "package": "com.android.settings"},
    ]
    assert device.resolve_package("mg android") == "com.android.mgandroid"
    assert device.resolve_package("com.android.mgandroid") == "com.android.mgandroid"
    assert device.resolve_package("com.example.missing") is None


def test_selector_supports_suffix_ids_text_contains_and_parent_clickable() -> None:
    tree = parse_ui_xml(HOME_XML.replace('resource-id="iv_logo"', 'resource-id="com.android.mgandroid:id/iv_logo"'))
    resolver = SelectorResolver()

    logo = resolver.resolve(tree, {"resource_id": "iv_logo"})
    assert logo.resource_id.endswith("/iv_logo")
    movie = resolver.resolve(
        tree,
        {"resource_id": "vod_category_name", "text": "PELÍCULA", "parent_clickable": True},
    )
    assert movie.text == "PELÍCULA"
    assert movie.tap_bounds() is not None
    with pytest.raises(SelectorNotFound):
        resolver.resolve(tree, {"text_contains": "not-present"})


def test_pack_actions_are_validated_and_expose_required_parameters() -> None:
    pack = KnowledgeRegistry(KNOWLEDGE).resolve("mgandroid")
    assert pack is not None
    actions = pack.action_specs
    assert actions["open_live"].parameters == frozenset()
    assert actions["select_channel"].parameters == frozenset({"channel"})
    compile_actions(pack.actions)


def test_session_exposes_and_executes_declarative_home_action() -> None:
    transport = FakeADBTransport()
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    frame = session.frame()
    assert any(action.verb == "open_live" for action in frame.actions)
    result = session.do("open_live")

    assert result.did == "open_live"
    assert any(kind == "tap" for kind, _ in transport.calls)


def test_session_exposes_and_executes_parameterized_knowledge_action() -> None:
    live_xml = """<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1920,1080]">
      <node text="ESPN HD" resource-id="channel_name" class="android.widget.TextView" clickable="true" bounds="[100,200][500,300]" />
      <node text="ESPN HD" resource-id="tv_live_title" class="android.widget.TextView" bounds="[10,10][300,80]" />
    </node></hierarchy>"""
    transport = FakeADBTransport(live_xml)
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    frame = session.frame()
    assert any(action.verb == "select_channel" for action in frame.actions)
    result = session.do("select_channel", text="ESPN")

    assert result.did == "select_channel"
    assert ("tap", ("300", "250")) in transport.calls


def test_session_uses_dpad_and_preserves_first_more_number() -> None:
    xml = HOME_XML.replace(
        'resource-id="iv_setting"',
        'resource-id="iv_setting" scrollable="true"',
    ).replace(
        "  </node>\n</hierarchy>",
        '    <node index="5" text="OTRO" resource-id="other" class="android.widget.TextView" clickable="true" bounds="[1300,300][1500,460]" />\n  </node>\n</hierarchy>',
    )
    transport = FakeADBTransport(xml)
    session = UISession(
        AndroidDevice(transport),
        KnowledgeRegistry(KNOWLEDGE),
        frame_builder=FrameBuilder(page_size=1),
    )

    first = session.frame()
    more = next(action for action in first.actions if action.kind == "more")
    session.do(more.number)
    second = session.frame(preserve_page=True)
    assert next(action for action in second.actions if action.kind == "more").number == more.number

    session.do("up")
    assert ("keyevent", ("KEYCODE_DPAD_UP",)) in transport.calls
