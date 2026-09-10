"""Lifecycle orchestration for the MGAndroid knowledge pack."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from android_agent_bridge.adb.transport import ADBError
from android_agent_bridge.devices.android import AndroidDevice
from android_agent_bridge.errors import KNOWLEDGE_PACK_NOT_FOUND, LIFECYCLE_TIMEOUT
from android_agent_bridge.knowledge.registry import KnowledgePack


class LifecycleError(RuntimeError):
    """A lifecycle transition could not reach its declared target state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    """Sanitized lifecycle observation; it never contains XML or bounds."""

    package: str
    activity: str
    screen: str

    def to_dict(self) -> dict[str, str]:
        return {
            "package": self.package,
            "activity": self.activity,
            "screen": self.screen,
        }


class MGAndroidLifecycle:
    """Open, recover and close MGAndroid using one device and one knowledge pack."""

    _package_pattern = re.compile(r"[A-Za-z][\w]*(?:\.[\w]+)+")

    def __init__(
        self,
        device: AndroidDevice,
        pack: KnowledgePack,
        *,
        session: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        default_timeout: float = 20.0,
        default_interval: float = 0.5,
        max_back: int = 5,
    ) -> None:
        if not pack.package_names:
            raise LifecycleError(KNOWLEDGE_PACK_NOT_FOUND, "MGAndroid pack has no package name")
        if default_timeout < 0 or default_interval < 0 or max_back < 0:
            raise ValueError("Lifecycle limits must be non-negative")
        self.device = device
        self.pack = pack
        self.session = session
        self.sleeper = sleeper
        self.clock = clock
        self.default_timeout = default_timeout
        self.default_interval = default_interval
        self.max_back = max_back
        self.package = pack.package_names[0]
        if not self._package_pattern.fullmatch(self.package):
            raise LifecycleError(KNOWLEDGE_PACK_NOT_FOUND, "MGAndroid pack has an invalid package name")

    def wait_ready(
        self,
        *,
        timeout: float | None = None,
        interval: float | None = None,
    ) -> LifecycleSnapshot:
        """Wait until MGAndroid is foreground and its pack recognizes the home state."""
        timeout = self.default_timeout if timeout is None else timeout
        interval = self.default_interval if interval is None else interval
        if timeout < 0 or interval < 0:
            raise ValueError("timeout and interval must be non-negative")

        deadline = self.clock() + timeout
        last = LifecycleSnapshot("unknown", "unknown", "unknown")
        while True:
            try:
                package, activity = self.device.foreground()
                last = LifecycleSnapshot(package, activity, "unknown")
                if package in self.pack.package_names:
                    snapshot = self.device.snapshot(package=package, activity=activity)
                    last = LifecycleSnapshot(package, activity, self.pack.matches_screen(snapshot.tree))
                    if last.screen == "home":
                        return last
            except (ADBError, ValueError):
                # Dumps can be unavailable or malformed while an app is starting.
                pass

            now = self.clock()
            if now >= deadline:
                raise LifecycleError(
                    LIFECYCLE_TIMEOUT,
                    f"MGAndroid was not ready: {last.package}/{last.screen}",
                )
            self.sleeper(min(interval, max(0.0, deadline - now)))

    def ensure_home(
        self,
        *,
        timeout: float | None = None,
        interval: float | None = None,
        max_back: int | None = None,
    ) -> LifecycleSnapshot:
        """Return home, using bounded back navigation before a clean restart."""
        max_back = self.max_back if max_back is None else max_back
        if max_back < 0:
            raise ValueError("max_back must be non-negative")

        try:
            current = self._observe()
            if current.package in self.pack.package_names and current.screen == "home":
                return current
        except (ADBError, ValueError):
            current = LifecycleSnapshot("unknown", "unknown", "unknown")

        if current.package in self.pack.package_names:
            for _ in range(max_back):
                self.device.transport.keyevent("KEYCODE_BACK")
                try:
                    current = self._observe()
                    if current.package in self.pack.package_names and current.screen == "home":
                        self._reset_session()
                        return current
                except (ADBError, ValueError):
                    continue

        return self.restart(timeout=timeout, interval=interval)

    def restart(
        self,
        *,
        timeout: float | None = None,
        interval: float | None = None,
    ) -> LifecycleSnapshot:
        """Force-stop and launch MGAndroid once, then wait for declared home."""
        self.device.open_app(self.package, fresh=True)
        self._reset_session()
        return self.wait_ready(timeout=timeout, interval=interval)

    def close(self) -> None:
        """Stop only MGAndroid; do not navigate or inspect another foreground app."""
        self.device.stop_app(self.package)
        self._reset_session()

    def _observe(self) -> LifecycleSnapshot:
        package, activity = self.device.foreground()
        if package not in self.pack.package_names:
            return LifecycleSnapshot(package, activity, "unknown")
        snapshot = self.device.snapshot(package=package, activity=activity)
        return LifecycleSnapshot(package, activity, self.pack.matches_screen(snapshot.tree))

    def _reset_session(self) -> None:
        if self.session is not None:
            self.session.reset()
