"""Build the real-user test kit in docs/user_test/kit/:

- northwind_2026_10.csv        the new month's data the participant works from
- answer_key.csv               the correct October numbers, for scoring manual errors
- timing_sheet.xlsx            fill-in sheet: manual vs app times, errors, ratings, quotes (with formulas)

The September deck (northwind_september_deck.pptx) is built separately:
    python scripts/run_pipeline.py --prev data/sample/northwind_2026_08.csv \
        --curr data/sample/northwind_2026_09.csv --pptx docs/user_test/kit/northwind_september_deck.pptx
"""
import csv
import shutil
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.context import RunContext  # noqa: E402
from app.facts import FactTable  # noqa: E402
from app.guard import guard  # noqa: E402
from app.tools import AnalysisTools  # noqa: E402

KIT = config.REPO_DIR / "docs" / "user_test" / "kit"
SEPT = config.SAMPLE_DIR / "northwind_2026_09.csv"
OCT = config.SAMPLE_DIR / "northwind_2026_10.csv"
PINK = PatternFill("solid", fgColor="FF2E93")
BLACK = PatternFill("solid", fgColor="0B0B0D")
INPUT = PatternFill("solid", fgColor="FDF2F8")
SLIDES_IN_DECK = 7


def answer_key() -> None:
    data = guard(SEPT, SEPT.name, OCT, OCT.name, RunContext())
    t = AnalysisTools(data, FactTable())
    t.define_metric("gross_profit_usd", "revenue_usd", "-", "cogs_usd")
    for m in ("revenue_usd", "orders", "units", "new_customers", "returns_usd", "marketing_usd"):
        t.compare_total(m)
    for d in data.dimensions:
        t.compare_by("revenue_usd", [d], top_n=25)
    t.compare_by("revenue_usd", ["region", "channel"], top_n=25)
    t.compare_ratio("returns_usd", "revenue_usd", "Return rate")
    t.compare_ratio("gross_profit_usd", "revenue_usd", "Gross margin")
    t.compare_ratio("returns_usd", "revenue_usd", "Return rate", "category")
    with (KIT / "answer_key.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "what", "value", "display", "how computed"])
        for fact in t.facts.facts.values():
            w.writerow([fact.id, fact.label, fact.value, fact.display, fact.source])
    print(f"answer_key.csv: {len(t.facts)} numbers")


def header(ws, row: int, cols: list[str]) -> None:
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = BLACK


def title(ws, text: str, sub: str) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=16, color="FF2E93")
    ws["A2"] = sub
    ws["A2"].font = Font(italic=True, color="6B6B75")
    ws["A2"].alignment = Alignment(wrap_text=True)


def timing_sheet() -> None:
    wb = Workbook()

    s = wb.active
    s.title = "1 Session"
    title(s, "Deck Autopilot: user test", "One row of facts about the session. Pink cells are for you to fill in.")
    rows = [("Date", ""), ("Participant (initials or name)", ""), ("Role / title", ""),
            ("Years in consulting or analytics", ""), ("How often do you refresh recurring decks?", ""),
            ("Typical time for one recurring deck refresh (their estimate, hours)", ""),
            ("OK to quote by name? (yes / initials only / no)", ""), ("Session format (in person / Zoom)", ""),
            ("Facilitator", "Jun Kim")]
    for i, (k, v) in enumerate(rows, 4):
        s.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = s.cell(row=i, column=2, value=v)
        c.fill = INPUT
    s.column_dimensions["A"].width = 62
    s.column_dimensions["B"].width = 40

    a = wb.create_sheet("2 Manual (today)")
    title(a, "Task A: update last month's deck by hand (15-minute timebox)",
          "Give: northwind_september_deck.pptx + northwind_2026_10.csv (Excel allowed). Ask them to update slides in order "
          "until the timebox ends. Record clock times as hh:mm:ss. Score numbers against answer_key.csv.")
    header(a, 4, ["Slide", "Start (hh:mm:ss)", "End (hh:mm:ss)", "Minutes", "Numbers updated",
                  "Numbers wrong vs answer key", "Title rewritten? (Y/N)", "Notes"])
    for i in range(SLIDES_IN_DECK):
        r = 5 + i
        a.cell(row=r, column=1, value=["Title", "Executive summary"][i] if i < 2 else f"Slide {i - 1}")
        for col in (2, 3, 5, 6, 7, 8):
            a.cell(row=r, column=col).fill = INPUT
        a.cell(row=r, column=4, value=f'=IF(AND(B{r}<>"",C{r}<>""),(C{r}-B{r})*1440,"")')
        a.cell(row=r, column=4).number_format = "0.0"
    last = 4 + SLIDES_IN_DECK
    a.cell(row=last + 2, column=1, value="Slides finished").font = Font(bold=True)
    a.cell(row=last + 2, column=4, value=f"=COUNT(D5:D{last})")
    a.cell(row=last + 3, column=1, value="Minutes used").font = Font(bold=True)
    a.cell(row=last + 3, column=4, value=f"=SUM(D5:D{last})")
    a.cell(row=last + 4, column=1, value="Minutes per slide").font = Font(bold=True)
    a.cell(row=last + 4, column=4, value=f'=IF(D{last + 2}>0,D{last + 3}/D{last + 2},"")')
    a.cell(row=last + 5, column=1, value=f"Projected minutes for the full {SLIDES_IN_DECK}-slide deck").font = Font(bold=True)
    a.cell(row=last + 5, column=4, value=f'=IF(D{last + 4}<>"",D{last + 4}*{SLIDES_IN_DECK},"")')
    a.cell(row=last + 6, column=1, value="Numbers wrong / numbers updated").font = Font(bold=True)
    a.cell(row=last + 6, column=4, value=f'=IF(SUM(E5:E{last})>0,SUM(F5:F{last})/SUM(E5:E{last}),"")')
    a.cell(row=last + 6, column=4).number_format = "0.0%"
    for r in range(last + 2, last + 7):
        a.cell(row=r, column=4).font = Font(bold=True, color="FF2E93")
        a.cell(row=r, column=4).number_format = a.cell(row=r, column=4).number_format if r == last + 6 else "0.0"
    for col, w in zip("ABCDEFGH", (22, 16, 16, 10, 16, 26, 22, 40)):
        a.column_dimensions[col].width = w

    b = wb.create_sheet("3 App")
    title(b, "Task B: same job with Deck Autopilot",
          "Open the app, say only 'Refresh the October deck with this data.' Do not explain the UI; note where they hesitate.")
    header(b, 4, ["Step", "Clock time (hh:mm:ss)", "Minutes from start", "Notes (hesitations, questions)"])
    steps = ["Start (app open, files on desktop)", "Data chosen (files dropped or sample clicked)",
             "Clicked Refresh my deck", "Deck ready on screen", "Finished reviewing slides (their call)",
             "Downloaded .pptx", "Opened .pptx and checked it (optional)"]
    for i, step in enumerate(steps):
        r = 5 + i
        b.cell(row=r, column=1, value=step)
        b.cell(row=r, column=2).fill = INPUT
        b.cell(row=r, column=4).fill = INPUT
        b.cell(row=r, column=3, value=f'=IF(B{r}<>"",(B{r}-$B$5)*1440,"")')
        b.cell(row=r, column=3).number_format = "0.0"
    b.cell(row=14, column=1, value="Minutes to a reviewed, downloaded deck").font = Font(bold=True)
    b.cell(row=14, column=3, value='=IF(B10<>"",(B10-B5)*1440,"")')
    b.cell(row=15, column=1, value="Could they use it without help? (Y / with one hint / N)").font = Font(bold=True)
    b.cell(row=15, column=3).fill = INPUT
    b.cell(row=16, column=1, value="Wrong numbers they found in the app's deck").font = Font(bold=True)
    b.cell(row=16, column=3).fill = INPUT
    b.cell(row=17, column=1, value="Did they click a bullet to trace its facts? (Y/N)").font = Font(bold=True)
    b.cell(row=17, column=3).fill = INPUT
    for r in (14,):
        b.cell(row=r, column=3).font = Font(bold=True, color="FF2E93")
        b.cell(row=r, column=3).number_format = "0.0"
    for col, w in zip("ABCD", (52, 22, 20, 50)):
        b.column_dimensions[col].width = w

    q = wb.create_sheet("4 Ratings + quotes")
    title(q, "After both tasks: ratings (1 = strongly disagree, 5 = strongly agree) and their words",
          "Read each statement aloud. Write quotes word for word; ask permission to use them.")
    header(q, 4, ["Statement", "Rating 1-5", "Why? (their words)"])
    statements = ["I trust the numbers in the app's deck.", "The app's slides say what I would have said.",
                  "I could hand this deck to a manager after a quick review.", "The app was easy to figure out.",
                  "I would use this for my recurring decks.",
                  "Seeing the facts behind each number makes me trust it more."]
    dv = DataValidation(type="whole", operator="between", formula1="1", formula2="5", showErrorMessage=True)
    q.add_data_validation(dv)
    for i, st in enumerate(statements):
        r = 5 + i
        q.cell(row=r, column=1, value=st)
        q.cell(row=r, column=2).fill = INPUT
        q.cell(row=r, column=3).fill = INPUT
        dv.add(q.cell(row=r, column=2))
    q.cell(row=12, column=1, value="Average rating").font = Font(bold=True)
    q.cell(row=12, column=2, value="=IFERROR(AVERAGE(B5:B10),\"\")")
    q.cell(row=12, column=2).number_format = "0.0"
    open_qs = ["Best quote (word for word):", "What would stop you from using it?", "What is missing?",
               "What would you pay / would your firm pay for this?"]
    for i, oq in enumerate(open_qs):
        q.cell(row=14 + i, column=1, value=oq).font = Font(bold=True)
        q.cell(row=14 + i, column=2).fill = INPUT
        q.merge_cells(start_row=14 + i, start_column=2, end_row=14 + i, end_column=3)
    for col, w in zip("ABC", (60, 12, 70)):
        q.column_dimensions[col].width = w

    m = wb.create_sheet("5 Summary")
    title(m, "Before vs after (fills in automatically)", "Copy these numbers into report section 7 (Impact).")
    header(m, 4, ["Measure", "Manual (today)", "Deck Autopilot", "Difference"])
    man, app = "'2 Manual (today)'", "'3 App'"
    rows = [
        ("Minutes for the full deck", f"={man}!D{last + 5}", f"={app}!C14", '=IF(AND(ISNUMBER(B5),ISNUMBER(C5)),B5-C5,"")'),
        ("Time saved (%)", "", "", '=IF(AND(ISNUMBER(B5),ISNUMBER(C5),B5>0),1-C5/B5,"")'),
        ("Wrong numbers per number written", f"={man}!D{last + 6}", "0 flagged as verified-but-wrong (check row 16 of App)", ""),
        ("Average rating (1-5)", "", "='4 Ratings + quotes'!B12", ""),
    ]
    for i, row in enumerate(rows):
        for j, v in enumerate(row, 1):
            m.cell(row=5 + i, column=j, value=v)
    m["D5"].number_format = "0.0"
    m["B5"].number_format = m["C5"].number_format = "0.0"
    m["D6"].number_format = "0%"
    m["B7"].number_format = "0.0%"
    m["B8"].number_format = m["C8"].number_format = "0.0"
    for r in range(5, 9):
        m.cell(row=r, column=1).font = Font(bold=True)
        m.cell(row=r, column=4).font = Font(bold=True, color="FF2E93")
    for col, w in zip("ABCD", (40, 20, 44, 16)):
        m.column_dimensions[col].width = w
    for ws in wb.worksheets:
        ws.sheet_properties.tabColor = "FF2E93"
    wb.save(KIT / "timing_sheet.xlsx")
    print("timing_sheet.xlsx written")


def main() -> None:
    KIT.mkdir(parents=True, exist_ok=True)
    shutil.copy(OCT, KIT / OCT.name)
    answer_key()
    timing_sheet()


if __name__ == "__main__":
    main()
