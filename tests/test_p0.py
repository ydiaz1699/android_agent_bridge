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
    compile_actions(pack.actions, selectors=pack.selectors)


def test_session_exposes_and_executes_declarative_home_action() -> None:
    transport = FakeADBTransport()
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    frame = session.frame()
    assert any(action.verb == "open_live" for action in frame.actions)
    result = session.do("open_live")

    assert result.did == "open_live"
    assert any(kind == "tap" for kind, _ in transport.calls)


def test_session_exposes_and_executes_parameterized_knowledge_action() -> None:
    live_xml = (ROOT / "examples" / "mgandroid_live.xml").read_text(encoding="utf-8")
    transport = FakeADBTransport(live_xml)
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    frame = session.frame()
    assert any(action.verb == "select_channel" for action in frame.actions)
    result = session.do("select_channel", text="ESPN")

    assert result.did == "select_channel"
    assert ("tap", ("300", "285")) in transport.calls


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



def test_actions_expand_named_pack_selectors_and_reject_unknown_fields() -> None:
    pack = KnowledgeRegistry(KNOWLEDGE).resolve("mgandroid")
    assert pack is not None
    open_live = pack.action_specs["open_live"]
    assert open_live.strategies[0]["resource_id"] == "vod_category_name"
    assert open_live.strategies[0]["text"] == "VIVO"

    with pytest.raises(ValueError, match="Unsupported strategy fields"):
        compile_actions(
            {
                "unsafe": {
                    "from": "home",
                    "intent": "navigate",
                    "strategies": [{"shell": "input tap 1 1"}],
                }
            }
        )


def test_ui_result_serializes_stable_error_code() -> None:
    transport = FakeADBTransport()
    session = UISession(AndroidDevice(transport), KnowledgeRegistry(KNOWLEDGE))

    result = session.do("does_not_exist")

    assert result.to_dict()["error_code"] == "action_not_found"
    assert result.to_dict()["error"] == "no action 'does_not_exist'"



def test_selector_supports_ancestor_hierarchy() -> None:
    tree = parse_ui_xml(HOME_XML)
    node = SelectorResolver().resolve(
        tree,
        {
            "text": "PELÍCULA",
            "ancestor": {"resource_id": "category_container", "class_name": "android.widget.LinearLayout"},
        },
    )
    assert node.text == "PELÍCULA"


def test_mgandroid_channels_fixture_covers_panel_category_channel_number_and_epg() -> None:
    xml = (ROOT / "examples" / "mgandroid_channels.xml").read_text(encoding="utf-8")
    tree = parse_ui_xml(xml)
    pack = KnowledgeRegistry(KNOWLEDGE).resolve("mgandroid")
    assert pack is not None
    resolver = SelectorResolver()

    panel = resolver.resolve(tree, pack.selectors["live"]["panel"][0])
    assert panel.scrollable is True
    assert panel.bounds is not None
    assert resolver.resolve(
        tree,
        {"resource_id": "channel_category", "text": "Deportes"},
    ).text == "Deportes"

    number = resolver.resolve(
        tree,
        {"resource_id": "channel_number", "text": "102", "ancestor": {"resource_id": "channel_row"}},
    )
    assert number.text == "102"

    channel = resolver.resolve(
        tree,
        {
            "resource_id": "channel_name",
            "text_contains": "FOX",
            "ancestor": {"resource_id": "channel_row", "class_name": "android.widget.LinearLayout"},
        },
    )
    assert channel.resource_id == "channel_name"
    assert channel.tap_bounds() is not None

    epg = resolver.resolve(tree, {"resource_id": "program_view", "text_contains": "Fútbol"})
    assert epg.text == "13:00 Fútbol en vivo"
    assert pack.matches_screen(tree) == "live"


def test_mgandroid_input_fixture_exposes_edittexts_password_and_submit() -> None:
    xml = (ROOT / "examples" / "mgandroid_input.xml").read_text(encoding="utf-8")
    tree = parse_ui_xml(xml)
    pack = KnowledgeRegistry(KNOWLEDGE).resolve("mgandroid")
    assert pack is not None
    resolver = SelectorResolver()

    search = resolver.resolve(tree, pack.selectors["input"]["search_field"][0])
    password = resolver.resolve(tree, pack.selectors["input"]["password_field"][0])
    submit = resolver.resolve(tree, pack.selectors["input"]["submit"][0])
    assert search.editable is True
    assert search.tap_bounds() is not None
    assert password.password is True
    assert submit.text == "Buscar"
    assert pack.matches_screen(tree) == "input"

    frame = FrameBuilder().build(tree, app="mgandroid", screen="input")
    assert any(action.verb == "type" and action.kind == "input" for action in frame.actions)
    assert any(action.verb == "type2" and action.kind == "input" for action in frame.actions)
    assert any(action.verb == "send" and action.kind == "submit" for action in frame.actions)


def test_mgandroid_unknown_fixture_does_not_claim_known_screen() -> None:
    xml = (ROOT / "examples" / "unknown_screen.xml").read_text(encoding="utf-8")
    tree = parse_ui_xml(xml)
    pack = KnowledgeRegistry(KNOWLEDGE).resolve("mgandroid")
    assert pack is not None

    assert pack.matches_screen(tree) == "unknown"
    frame = FrameBuilder().build(tree, app="mgandroid", screen=pack.matches_screen(tree))
    assert frame.screen == "unknown"
    assert "Cargando contenido" in frame.read


def test_named_pack_selectors_support_region_and_ancestor_boundaries() -> None:
    xml = (ROOT / "examples" / "mgandroid_channels.xml").read_text(encoding="utf-8")
    tree = parse_ui_xml(xml)
    resolver = SelectorResolver()

    panel = resolver.resolve(tree, {"resource_id": "channel_panel", "region": {"left": 0, "top": 100, "right": 900, "bottom": 1080}})
    assert panel.resource_id == "channel_panel"
    channel = resolver.resolve(
        tree,
        {
            "resource_id": "channel_name",
            "text": "ESPN HD",
            "ancestor": {"resource_id": "channel_row", "class_name": "android.widget.LinearLayout"},
        },
    )
    assert channel.text == "ESPN HD"
