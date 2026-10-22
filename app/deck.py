"""The deck the Storyliner writes (structured output) — text plus fact IDs, never raw chart numbers.

Charts only hold fact IDs; the renderer looks the values up in the fact table, so a chart
can't show a number the data doesn't contain.
"""
from typing import Literal

from pydantic import BaseModel, Field


class Bullet(BaseModel):
    text: str = Field(description="One short sentence. Numbers copied exactly from fact display values.")
    fact_ids: list[str] = Field(description="Every fact whose number appears in the text.")


class ChartPoint(BaseModel):
    label: str = Field(description="Bar label, e.g. 'Northeast' or 'Sep'.")
    fact_id: str


class Chart(BaseModel):
    type: Literal["column", "bar"] = Field(description="column = compare values; bar = ranked changes.")
    title: str = Field(description="What the bars measure, with unit, e.g. 'Revenue change by region, $'.")
    points: list[ChartPoint] = Field(description="3-8 points, all facts in the same unit.")


class Slide(BaseModel):
    title: str = Field(description="Action title: the so-what in one sentence, max ~15 words.")
    title_fact_ids: list[str]
    bullets: list[Bullet] = Field(description="2-4 supporting bullets.")
    chart: Chart | None
    speaker_notes: str = Field(description="1-2 sentences for the presenter; likely cause if known.")


class Deck(BaseModel):
    deck_title: str
    subtitle: str = Field(description="Client and periods compared, e.g. 'Monthly business review: Sep vs Oct 2026'.")
    executive_summary: list[Bullet] = Field(description="3-5 bullets, the whole story in brief.")
    slides: list[Slide] = Field(description="4-6 content slides, most important first.")
