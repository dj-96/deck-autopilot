"""Storyliner agent: findings + fact table -> a structured deck (action titles, bullets, chart specs)."""
import json
from pathlib import Path

from app.context import RunContext
from app.deck import Deck
from app.facts import FactTable
from app.llm import call_model

PROMPT = (Path(__file__).parent / "prompts" / "storyliner.md").read_text(encoding="utf-8")


class StorylinerSession:
    """Keeps the conversation so fix-up rounds reuse the cached prefix (facts + first draft)."""

    def __init__(self, findings: list[dict], facts: FactTable, prev_label: str, curr_label: str,
                 ctx: RunContext) -> None:
        self.ctx = ctx
        fact_lines = "\n".join(f"{f.id} | {f.display} | {f.label}" for f in facts.facts.values())
        self.items: list = [{"role": "user", "content": (
            f"Periods: {prev_label} (previous) vs {curr_label} (current).\n\n"
            f"## Analyst findings (JSON)\n{json.dumps(findings, indent=1)}\n\n"
            f"## Fact table (ID | display value | label)\n{fact_lines}\n\n"
            "Write the deck.")}]
        self.round = 0

    def _call(self) -> Deck:
        self.round += 1
        resp, gateway = call_model("storyliner", self.ctx.meter, structured=Deck,
                                   instructions=PROMPT, input=self.items)
        deck = resp.output_parsed
        if deck is None:
            raise RuntimeError("Storyliner returned no deck (refusal or empty output).")
        last = self.ctx.meter.calls[-1]
        self.ctx.log("storyliner", "model_call",
                     f"Draft {self.round}: {len(deck.slides)} slides via {gateway}",
                     tokens={"input": last.input_tokens, "cached": last.cached_tokens,
                             "output": last.output_tokens})
        self.items.append({"role": "assistant", "content": deck.model_dump_json()})
        return deck

    def draft(self) -> Deck:
        return self._call()

    def fix(self, problems: list[str]) -> Deck:
        self.items.append({"role": "user", "content": (
            "The fact-checker rejected these numbers:\n- " + "\n- ".join(problems) +
            "\n\nReturn the full deck again with each problem fixed: use the exact display value of a "
            "fact you cite, or remove the number. Change nothing else.")})
        return self._call()
