"""Declarative workflow data; execution remains in the single UI session."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    command: str


@dataclass(frozen=True, slots=True)
class Workflow:
    name: str
    steps: tuple[WorkflowStep, ...]

    def render(self, args: list[str]) -> list[str]:
        """Substitute $1, $2 and $* without storing coordinates or secrets."""
        rendered: list[str] = []
        for step in self.steps:
            value = step.command.replace("$*", " ".join(args))
            for index, argument in enumerate(args, start=1):
                value = value.replace(f"${index}", argument)
            rendered.append(value)
        return rendered
