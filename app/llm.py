"""One place to call the model: Portkey first, OpenAI as automatic fallback, every token metered.

Every agent calls `call_model(...)` with a `UsageMeter`. The meter records input,
cached-input, and output tokens per call, prices them, and refuses new calls once
the run's token cap is hit.
"""
from dataclasses import dataclass, field

import openai
from openai import OpenAI

from app import config


class BudgetExceeded(RuntimeError):
    """Raised before a call that would run past the per-run token cap."""


class NoGatewayAvailable(RuntimeError):
    """Raised when no API key is configured, or every gateway failed."""


# --- Usage metering ----------------------------------------------------------

@dataclass
class CallRecord:
    agent: str
    gateway: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        # OpenAI counts cached tokens inside input_tokens, so bill them separately.
        uncached = self.input_tokens - self.cached_tokens
        p = config.PRICES
        return (uncached * p["input"] + self.cached_tokens * p["cached_input"]
                + self.output_tokens * p["output"]) / 1e6


@dataclass
class UsageMeter:
    max_tokens: int = config.MAX_TOKENS_PER_RUN
    calls: list[CallRecord] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.calls)

    def check_budget(self) -> None:
        if self.total_tokens >= self.max_tokens:
            raise BudgetExceeded(
                f"Run stopped: {self.total_tokens:,} tokens used, cap is {self.max_tokens:,}.")

    def record(self, agent: str, gateway: str, usage) -> CallRecord:
        details = getattr(usage, "input_tokens_details", None)
        rec = CallRecord(
            agent=agent,
            gateway=gateway,
            input_tokens=usage.input_tokens,
            cached_tokens=getattr(details, "cached_tokens", 0) or 0,
            output_tokens=usage.output_tokens,
        )
        self.calls.append(rec)
        return rec

    def summary(self) -> dict:
        return {
            "calls": len(self.calls),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "cached_tokens": sum(c.cached_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "cost_usd": round(sum(c.cost_usd for c in self.calls), 6),
            "gateways": sorted({c.gateway for c in self.calls}),
            "by_agent": [vars(c) | {"cost_usd": round(c.cost_usd, 6)} for c in self.calls],
        }


# --- Gateways ----------------------------------------------------------------

# Once Portkey fails with a budget/auth error we skip it for the rest of the process,
# so a dead course key costs one failed request, not one per agent call.
_disabled: dict[str, str] = {}
_clients: dict[str, OpenAI] = {}


def _make_client(name: str) -> OpenAI | None:
    if name == "portkey":
        key = config.env("PORTKEY_API_KEY")
        if not key:
            return None
        return OpenAI(api_key=key, base_url=config.PORTKEY_BASE_URL,
                      default_headers={"x-portkey-api-key": key},
                      max_retries=1, timeout=config.REQUEST_TIMEOUT_S)
    key = config.env("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key, max_retries=1, timeout=config.REQUEST_TIMEOUT_S)


def gateway_order() -> list[str]:
    """Gateways to try, in order. LLM_GATEWAY=portkey|openai pins one; default 'auto'."""
    pinned = (config.env("LLM_GATEWAY") or "auto").lower()
    if pinned in ("portkey", "openai"):
        return [pinned]
    return ["portkey", "openai"]


def _client(name: str) -> OpenAI | None:
    if name not in _clients:
        client = _make_client(name)
        if client is None:
            return None
        _clients[name] = client
    return _clients[name]


def _should_fall_back(err: Exception) -> bool:
    """Budget, auth, rate-limit, server, and network errors move us to the next gateway.

    A 400/404/422 means our request is wrong; switching gateways would not help,
    so that error is raised instead.
    """
    if isinstance(err, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(err, openai.APIStatusError):
        return err.status_code not in (400, 404, 422)
    return False


def call_model(agent: str, meter: UsageMeter, *, structured=None, **kwargs):
    """Call the Responses API for one agent step.

    structured: optional Pydantic model; if given, uses responses.parse and the
    result's `.output_parsed` holds the validated object.
    Returns (response, gateway_name).
    """
    meter.check_budget()
    kwargs.setdefault("max_output_tokens", config.MAX_OUTPUT_TOKENS_PER_CALL)
    errors = []
    for name in gateway_order():
        if name in _disabled:
            errors.append(f"{name}: skipped ({_disabled[name]})")
            continue
        client = _client(name)
        if client is None:
            errors.append(f"{name}: no API key set")
            continue
        try:
            if structured is not None:
                resp = client.responses.parse(model=config.MODEL_NAME, text_format=structured, **kwargs)
            else:
                resp = client.responses.create(model=config.MODEL_NAME, **kwargs)
        except Exception as err:  # noqa: BLE001 - we re-raise anything we can't route around
            if not _should_fall_back(err):
                raise
            reason = f"{type(err).__name__} {getattr(err, 'status_code', '')}".strip()
            _disabled[name] = reason
            errors.append(f"{name}: {reason}")
            continue
        meter.record(agent, name, resp.usage)
        return resp, name
    raise NoGatewayAvailable("No model gateway worked. " + "; ".join(errors))


def gateway_status() -> dict:
    """For the UI and README check: which keys are present and which gateways are disabled."""
    return {
        "order": gateway_order(),
        "keys_present": {"portkey": bool(config.env("PORTKEY_API_KEY")),
                         "openai": bool(config.env("OPENAI_API_KEY"))},
        "env_files_found": [str(p) for p in config.ENV_FILES if p.is_file()],
        "disabled": dict(_disabled),
    }
