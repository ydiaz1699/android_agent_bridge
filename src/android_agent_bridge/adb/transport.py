"""ADB transport boundary used by every higher layer."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class ADBError(RuntimeError):
    """Raised when an ADB command cannot be completed."""


class ADBTransport(Protocol):
    """Minimal transport contract for phones, emulators and TVs."""

    def run(self, args: Sequence[str], *, timeout: float = 30.0) -> str:
        ...

    def shell(self, args: Sequence[str], *, timeout: float = 30.0) -> str:
        ...

    def dump_ui(self, *, timeout: float = 30.0) -> str:
        ...

    def tap(self, x: int, y: int) -> None:
        ...

    def keyevent(self, key: str) -> None:
        ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        ...

    def input_text(self, text: str) -> None:
        ...


@dataclass(slots=True)
class SubprocessADB:
    """ADB implementation using the locally installed platform tools."""

    serial: str | None = None
    executable: str = "adb"

    def _command(self, args: Sequence[str]) -> list[str]:
        command = [self.executable]
        if self.serial:
            command.extend(("-s", self.serial))
        command.extend(str(arg) for arg in args)
        return command

    def run(self, args: Sequence[str], *, timeout: float = 30.0) -> str:
        command = self._command(args)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise ADBError("adb was not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ADBError(f"ADB timed out: {' '.join(command)}") from exc

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise ADBError(f"ADB command failed ({result.returncode}): {detail}")
        return result.stdout.strip()

    def shell(self, args: Sequence[str], *, timeout: float = 30.0) -> str:
        return self.run(("shell", *args), timeout=timeout)

    def dump_ui(self, *, timeout: float = 30.0) -> str:
        remote_path = "/sdcard/android_agent_bridge_window.xml"
        self.shell(("uiautomator", "dump", remote_path), timeout=timeout)
        return self.shell(("cat", remote_path), timeout=timeout)

    def tap(self, x: int, y: int) -> None:
        self.shell(("input", "tap", str(x), str(y)))

    def keyevent(self, key: str) -> None:
        self.shell(("input", "keyevent", key))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.shell(("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)))

    def input_text(self, text: str) -> None:
        # The device-side input grammar is intentionally kept behind the transport.
        # A future IME/clipboard implementation can replace this without changing UI code.
        escaped = text.replace("%", "%25").replace(" ", "%s")
        self.shell(("input", "text", escaped))

    def devices(self) -> list[str]:
        output = self.run(("devices",))
        return [
            line.split("\t", 1)[0]
            for line in output.splitlines()[1:]
            if "\tdevice" in line
        ]
