"""Stable error codes shared by UI sessions and adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BridgeError:
    """A safe, serializable bridge error."""

    code: str
    message: str

    def as_text(self) -> str:
        return f"{self.code}: {self.message}"


ACTION_NOT_FOUND = "action_not_found"
ACTION_NOT_SUPPORTED = "action_not_supported"
ACTION_FAILED = "action_failed"
INPUT_REQUIRED = "input_required"
PAGINATION_END = "pagination_end"
KNOWLEDGE_PACK_NOT_FOUND = "knowledge_pack_not_found"
VERIFICATION_FAILED = "verification_failed"
LIFECYCLE_TIMEOUT = "lifecycle_timeout"
APP_NOT_READY = "app_not_ready"
ADB_FAILED = "adb_failed"
