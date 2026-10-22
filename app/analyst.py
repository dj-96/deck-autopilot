"""Analyst agent: calls the Python tools in a loop until it submits findings backed by fact IDs."""
import json
from dataclasses import dataclass
from pathlib import Path

from app.context import RunContext
from app.facts import FactTable
from app.guard import GuardedData
from app.llm import call_model
from app.tools import TOOL_SCHEMAS, AnalysisTools

PROMPT = (Path(__file__).parent / "prompts" / "analyst.md").read_text(encoding="utf-8")
MAX_TURNS = 10  # model round-trips; stops a loop that never submits
MAX_TOOL_CALLS = 30


class AnalystFailed(RuntimeError):
    pass


@dataclass
class AnalystResult:
    facts: FactTable
    findings: list[dict]
    tool_calls: int
    turns: int


def run_analyst(data: GuardedData, ctx: RunContext) -> AnalystResult:
    facts = FactTable()
    tools = AnalysisTools(data, facts)
    # Static prompt + tool schemas come first so repeat runs hit the prompt cache.
    items: list = [{"role": "user", "content":
                    f"Analyze the change from {data.prev_label} to {data.curr_label} and submit findings."}]
    tool_calls = 0
    for turn in range(1, MAX_TURNS + 1):
        resp, gateway = call_model("analyst", ctx.meter, instructions=PROMPT, input=items,
                                   tools=TOOL_SCHEMAS, parallel_tool_calls=True)
        calls = [o for o in resp.output if o.type == "function_call"]
        last = ctx.meter.calls[-1]
        ctx.log("analyst", "model_call",
                f"Turn {turn}: {len(calls)} tool call(s) via {gateway}",
                tokens={"input": last.input_tokens, "cached": last.cached_tokens, "output": last.output_tokens})
        if not calls:
            # Model answered in text instead of submitting; nudge once per turn.
            items += [o.model_dump(exclude_none=True) for o in resp.output]
            items.append({"role": "user", "content": "Finish by calling submit_findings with fact IDs."})
            continue
        items += [o.model_dump(exclude_none=True) for o in resp.output]
        for call in calls:
            tool_calls += 1
            if tool_calls > MAX_TOOL_CALLS:
                output = json.dumps({"error": "Tool-call limit reached. Call submit_findings now."})
            else:
                output = tools.call(call.name, call.arguments)
            ctx.log("analyst", "tool_call", f"{call.name}({_short(call.arguments)})",
                    result=_short(output, 300))
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": output})
        if tools.submitted is not None:
            ctx.log("analyst", "done", f"Submitted {len(tools.submitted)} findings citing "
                                       f"{len({i for f in tools.submitted for i in f['fact_ids']})} facts; "
                                       f"{len(facts)} facts computed.")
            return AnalystResult(facts, tools.submitted, tool_calls, turn)
    raise AnalystFailed(f"Analyst did not submit findings within {MAX_TURNS} turns.")


def _short(text: str, limit: int = 120) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "..."
