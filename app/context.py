"""State shared by every step of one run: token meter, step trace, and safety log."""
import time
from dataclasses import dataclass, field

from app.llm import UsageMeter


@dataclass
class RunContext:
    meter: UsageMeter = field(default_factory=UsageMeter)
    trace: list[dict] = field(default_factory=list)  # what each agent did, in order (for the UI and report)
    safety: list[dict] = field(default_factory=list)  # every defense that fired

    def log(self, agent: str, kind: str, detail: str, **extra) -> None:
        self.trace.append({"t": round(time.time(), 3), "agent": agent, "kind": kind,
                           "detail": detail, **extra})

    def safety_event(self, defense: str, detail: str, **extra) -> None:
        self.safety.append({"defense": defense, "detail": detail, **extra})
        self.log("guard" if defense.startswith("guard") else defense, "safety", detail)
