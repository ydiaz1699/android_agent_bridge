"""Optional REST adapter over the same frame/session contracts."""

from __future__ import annotations

from typing import Any


def create_app(session: Any):
    """Create a FastAPI adapter without making FastAPI a core dependency."""
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("Install android-agent-bridge[rest] to use the REST adapter") from exc

    app = FastAPI(title="android-agent-bridge", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/frame")
    def frame() -> dict[str, Any]:
        return session.frame().to_dict()

    @app.post("/ui/do")
    def do(action: str, text: str | None = None) -> dict[str, Any]:
        return session.do(action, text).to_dict()

    return app
