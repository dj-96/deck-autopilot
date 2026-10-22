"""The fact table: every number a slide may use, computed by Python, each with an ID.

Agents cite facts by ID (F1, F2, ...). The fact-checker later compares every number
written on a slide against this table, so the model can't invent or round a number
into something the data doesn't say.
"""
from dataclasses import asdict, dataclass

UNITS = ("usd", "count", "pct", "pp")  # pct = percent value (7.7 means 7.7%); pp = percentage points
MAX_FACTS = 200


@dataclass
class Fact:
    id: str
    label: str  # plain English, e.g. "Revenue, Northeast, 2026-10"
    value: float
    unit: str
    source: str  # how it was computed, e.g. "sum(revenue_usd) where region=Northeast"

    @property
    def display(self) -> str:
        return fmt(self.value, self.unit, signed=self.label.startswith("Change"))

    def to_dict(self) -> dict:
        return asdict(self) | {"display": self.display}


def fmt(value: float, unit: str, signed: bool = False) -> str:
    sign = "+" if signed and value > 0 else ("-" if value < 0 else "")
    v = abs(value)
    if unit == "usd":
        if v >= 1e6:
            body = f"${v / 1e6:.2f}M"
        elif v >= 1e3:
            body = f"${v / 1e3:.0f}K"
        else:
            body = f"${v:,.0f}"
    elif unit == "count":
        body = f"{v:,.0f}"
    elif unit == "pct":
        body = f"{v:.1f}%"
    elif unit == "pp":
        body = f"{v:.1f} pp"
    else:
        body = f"{v:,.2f}"
    return sign + body


class FactTable:
    def __init__(self) -> None:
        self.facts: dict[str, Fact] = {}
        self._by_label: dict[str, str] = {}

    def add(self, label: str, value: float, unit: str, source: str) -> Fact:
        if unit not in UNITS:
            raise ValueError(f"unknown unit {unit}")
        if label in self._by_label:  # same question asked twice -> same fact ID
            return self.facts[self._by_label[label]]
        if len(self.facts) >= MAX_FACTS:
            raise OverflowError(f"Fact table is full ({MAX_FACTS}). Submit findings with the facts you have.")
        fact = Fact(f"F{len(self.facts) + 1}", label, round(float(value), 4), unit, source)
        self.facts[fact.id] = fact
        self._by_label[label] = fact.id
        return fact

    def get(self, fact_id: str) -> Fact | None:
        return self.facts.get(fact_id)

    def __len__(self) -> int:
        return len(self.facts)

    def to_list(self) -> list[dict]:
        return [f.to_dict() for f in self.facts.values()]
