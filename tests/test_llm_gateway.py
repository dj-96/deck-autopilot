"""Offline tests for the gateway fallback and the per-run token cap (no network, no keys used)."""
from types import SimpleNamespace

import httpx2 as httpx  # the HTTP library openai 3.x is built on
import openai
import pytest

from app import llm


def _usage(inp=100, cached=0, out=20):
    return SimpleNamespace(input_tokens=inp, output_tokens=out,
                           input_tokens_details=SimpleNamespace(cached_tokens=cached))


def _status_error(code: int, msg: str = "Budget limit exceeded"):
    req = httpx.Request("POST", "https://api.portkey.ai/v1/responses")
    return openai.APIStatusError(msg, response=httpx.Response(code, request=req), body=None)


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0
        self.responses = SimpleNamespace(create=self._create, parse=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(usage=_usage(), output_text="ok")


@pytest.mark.parametrize("code", [412, 429, 401])
def test_portkey_budget_and_auth_errors_trigger_fallback(monkeypatch, code):
    # 412 is what Portkey actually returned when the course key ran out of budget.
    _install(monkeypatch, FakeClient(_status_error(code)), FakeClient())
    assert llm.call_model("t", llm.UsageMeter(), input="hi")[1] == "openai"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(llm, "_disabled", {})
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.delenv("LLM_GATEWAY", raising=False)


def _install(monkeypatch, portkey, openai_client):
    monkeypatch.setattr(llm, "_make_client",
                        lambda name: {"portkey": portkey, "openai": openai_client}[name])


def test_uses_portkey_when_it_works(monkeypatch):
    portkey, oai = FakeClient(), FakeClient()
    _install(monkeypatch, portkey, oai)
    _, gateway = llm.call_model("t", llm.UsageMeter(), input="hi")
    assert gateway == "portkey" and oai.calls == 0


def test_falls_back_to_openai_when_portkey_out_of_budget(monkeypatch):
    portkey, oai = FakeClient(_status_error(429)), FakeClient()
    _install(monkeypatch, portkey, oai)
    meter = llm.UsageMeter()
    _, gateway = llm.call_model("t", meter, input="hi")
    assert gateway == "openai"
    # Second call skips the dead Portkey key instead of failing again.
    llm.call_model("t", meter, input="hi")
    assert portkey.calls == 1 and oai.calls == 2
    assert [c.gateway for c in meter.calls] == ["openai", "openai"]


def test_falls_back_when_portkey_key_missing(monkeypatch):
    oai = FakeClient()
    _install(monkeypatch, None, oai)
    _, gateway = llm.call_model("t", llm.UsageMeter(), input="hi")
    assert gateway == "openai"


def test_bad_request_is_raised_not_hidden(monkeypatch):
    portkey, oai = FakeClient(_status_error(400, "bad schema")), FakeClient()
    _install(monkeypatch, portkey, oai)
    with pytest.raises(openai.APIStatusError):
        llm.call_model("t", llm.UsageMeter(), input="hi")
    assert oai.calls == 0


def test_no_keys_gives_clear_error(monkeypatch):
    _install(monkeypatch, None, None)
    with pytest.raises(llm.NoGatewayAvailable, match="no API key"):
        llm.call_model("t", llm.UsageMeter(), input="hi")


def test_token_cap_stops_runaway_run(monkeypatch):
    _install(monkeypatch, FakeClient(), FakeClient())
    meter = llm.UsageMeter(max_tokens=200)  # each fake call uses 120 tokens
    llm.call_model("t", meter, input="hi")
    llm.call_model("t", meter, input="hi")
    with pytest.raises(llm.BudgetExceeded):
        llm.call_model("t", meter, input="hi")
    assert len(meter.calls) == 2


def test_cost_bills_cached_tokens_at_cached_rate():
    rec = llm.CallRecord("t", "openai", input_tokens=1_000_000, cached_tokens=400_000, output_tokens=100_000)
    # 600k uncached * $0.10 + 400k cached * $0.01 + 100k out * $0.50, per 1M
    assert rec.cost_usd == pytest.approx(0.06 + 0.004 + 0.05)
