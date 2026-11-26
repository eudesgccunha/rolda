"""A small support agent instrumented with OpenTelemetry GenAI spans.

The model is simulated: a scripted, seeded stand-in that returns plausible
token counts and sleeps for a plausible latency. Tools and control flow are
real code. Faults are injected at the tool and model level.
"""

import json
import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from random import Random

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Span, Status, StatusCode

SERVICE_NAME = "support-agent"
MODEL = "support-sim-1"
TOOL_TIMEOUT_MESSAGE = "timeout after 30s"
RATE_LIMIT_MESSAGE = "429 rate limited"

# Fault kinds, one per session at most.
HEALTHY = "healthy"
TIMEOUT = "tool_timeout"
RATE_LIMIT = "rate_limit"
LOOP = "tool_loop"
LATENCY = "latency_outlier"
BLOWUP = "token_blowup"

FAULT_WEIGHTS: list[tuple[str, float]] = [
    (TIMEOUT, 0.08),
    (RATE_LIMIT, 0.03),
    (LOOP, 0.04),
    (LATENCY, 0.03),
    (BLOWUP, 0.03),
]


class ToolTimeoutError(TimeoutError):
    """The tool did not answer in time."""


class RateLimitedError(RuntimeError):
    """The tool backend rejected the call with HTTP 429."""


class CountingExporter(SpanExporter):
    """Wraps an exporter and counts export results."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner
        self.ok = 0
        self.failed = 0

    def export(self, spans: "list[ReadableSpan]") -> SpanExportResult:
        result = self._inner.export(spans)
        if result is SpanExportResult.SUCCESS:
            self.ok += 1
        else:
            self.failed += 1
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def setup_tracing(endpoint: str) -> tuple[TracerProvider, CountingExporter]:
    """Create a tracer provider that exports over OTLP/HTTP."""
    exporter = CountingExporter(OTLPSpanExporter(endpoint=endpoint))
    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME})
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider, exporter


def pick_fault(rng: Random) -> str:
    """Draw the fault kind of one session."""
    draw = rng.random()
    total = 0.0
    for kind, weight in FAULT_WEIGHTS:
        total += weight
        if draw < total:
            return kind
    return HEALTHY


def lognormal_ms(rng: Random, median_ms: float, sigma: float) -> float:
    """Seeded log-normal sample, in milliseconds."""
    return rng.lognormvariate(math.log(median_ms), sigma)


# ---------------------------------------------------------------- tools

ORDERS: dict[str, list[dict[str, str]]] = {
    f"C{n}": [
        {
            "order_id": f"A{1000 + n * 3 + k}",
            "status": ("shipped", "delivered", "processing")[(n + k) % 3],
            "total": f"{20 + (n * 7 + k * 13) % 180}.00",
        }
        for k in range(2)
    ]
    for n in range(1, 41)
}

ADDRESSES: dict[str, str] = {}


def search_orders(customer_id: str) -> list[dict[str, str]]:
    """Look up the orders of a customer."""
    return ORDERS.get(customer_id, [])


def get_refund_policy(order_status: str) -> str:
    """Return the refund rule for an order status."""
    if order_status == "delivered":
        return "refund allowed within 30 days of delivery"
    if order_status == "shipped":
        return "refund after the parcel is returned"
    return "order can be cancelled for a full refund"


def issue_refund(order_id: str, amount: str) -> str:
    """Issue a refund and return a refund reference."""
    return f"RF-{order_id}-{amount.replace('.', '')}"


def update_address(customer_id: str, address: str) -> str:
    """Store a new shipping address for a customer."""
    ADDRESSES[customer_id] = address
    return f"address updated for {customer_id}"


TOOLS = {
    "search_orders": search_orders,
    "get_refund_policy": get_refund_policy,
    "issue_refund": issue_refund,
    "update_address": update_address,
}


# ------------------------------------------------------ simulated model


@dataclass
class Completion:
    """What the simulated model returns for one call."""

    input_tokens: int
    output_tokens: int
    latency_ms: float


class SimulatedModel:
    """Scripted stand-in for an LLM. No network, no API key."""

    def __init__(self, rng: Random) -> None:
        self._rng = rng

    def complete(
        self,
        context_tokens: int,
        output_tokens: int,
        *,
        latency_factor: float = 1.0,
        input_factor: float = 1.0,
    ) -> Completion:
        rng = self._rng
        tokens_in = int(context_tokens * input_factor * rng.uniform(0.9, 1.1))
        tokens_out = max(8, int(output_tokens * rng.uniform(0.7, 1.4)))
        base = lognormal_ms(rng, 90.0, 0.45) + tokens_out * 0.9
        latency = min(base, 450.0) * latency_factor
        time.sleep(latency / 1000)
        return Completion(tokens_in, tokens_out, latency)


# ---------------------------------------------------------------- agent


@dataclass
class Session:
    """The plan and fault injection of one customer session."""

    intent: str
    customer_id: str
    fault: str
    steps: list[tuple[str, dict[str, str]]] = field(default_factory=list)


@dataclass
class Outcome:
    """Result of a session."""

    fault: str
    tool_calls: int
    failed: bool


def build_session(rng: Random) -> Session:
    """Draw a customer request and the fault for this session."""
    intent = rng.choice(["order_status", "refund", "change_address"])
    customer = f"C{rng.randint(1, 40)}"
    order = ORDERS[customer][0]
    steps: list[tuple[str, dict[str, str]]] = [
        ("search_orders", {"customer_id": customer})
    ]
    if intent == "refund":
        steps.append(("get_refund_policy", {"order_status": order["status"]}))
        steps.append(
            (
                "issue_refund",
                {"order_id": order["order_id"], "amount": order["total"]},
            )
        )
    elif intent == "change_address":
        street = rng.randint(1, 99)
        steps.append(
            (
                "update_address",
                {
                    "customer_id": customer,
                    "address": f"{street} Market Street",
                },
            )
        )
    return Session(intent, customer, pick_fault(rng), steps)


class SupportAgent:
    """Runs one session as an `invoke_agent` span with child spans."""

    def __init__(self, rng: Random, tracer: trace.Tracer | None = None):
        self._rng = rng
        self._tracer = tracer or trace.get_tracer("support_agent")
        self._model = SimulatedModel(rng)

    def handle(self, session: Session) -> Outcome:
        rng = self._rng
        steps = list(session.steps)
        if session.fault == LOOP:
            name, args = steps[0]
            steps = [(name, args)] * rng.randint(6, 10)
        # Which tool call and which model call carry the fault.
        faulty_tool = rng.randrange(len(steps))
        faulty_chat = rng.randrange(len(steps) + 1)
        calls = 0
        failed = False
        context = rng.randint(400, 700)
        with self._tracer.start_as_current_span(
            f"invoke_agent {SERVICE_NAME}",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": SERVICE_NAME,
                "gen_ai.request.model": MODEL,
                "support.intent": session.intent,
            },
        ):
            for index, (tool, args) in enumerate(steps):
                self._chat(context, 40, session.fault, index == faulty_chat)
                context += 120
                calls += 1
                try:
                    result = self._call_tool(
                        tool, args, session.fault, index == faulty_tool
                    )
                except (ToolTimeoutError, RateLimitedError):
                    failed = True
                    break
                context += len(json.dumps(result)) // 3
            reply = 90 if failed else 140
            last = len(steps) == faulty_chat
            self._chat(context, reply, session.fault, last)
        return Outcome(session.fault, calls, failed)

    def _chat(
        self, context: int, output: int, fault: str, faulty: bool
    ) -> None:
        latency = 1.0
        blowup = 1.0
        if faulty and fault == LATENCY:
            latency = self._rng.uniform(3.0, 6.0)
        if faulty and fault == BLOWUP:
            blowup = self._rng.uniform(5.0, 10.0)
        with self._tracer.start_as_current_span(
            f"chat {MODEL}",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "simulated",
                "gen_ai.request.model": MODEL,
                "gen_ai.agent.name": SERVICE_NAME,
            },
        ) as span:
            done = self._model.complete(
                context,
                output,
                latency_factor=latency,
                input_factor=blowup,
            )
            span.set_attribute("gen_ai.usage.input_tokens", done.input_tokens)
            span.set_attribute(
                "gen_ai.usage.output_tokens", done.output_tokens
            )

    def _call_tool(
        self, name: str, args: dict[str, str], fault: str, faulty: bool
    ) -> object:
        rng = self._rng
        with self._tool_span(name, args) as span:
            time.sleep(lognormal_ms(rng, 25.0, 0.5) / 1000)
            if faulty and fault == TIMEOUT:
                # The 30s is the reported value, not a real wait.
                time.sleep(0.15)
                raise ToolTimeoutError(TOOL_TIMEOUT_MESSAGE)
            if faulty and fault == RATE_LIMIT:
                raise RateLimitedError(RATE_LIMIT_MESSAGE)
            result = TOOLS[name](**args)
            span.set_status(Status(StatusCode.OK))
            return result

    @contextmanager
    def _tool_span(self, name: str, args: dict[str, str]) -> Iterator[Span]:
        with self._tracer.start_as_current_span(
            f"execute_tool {name}",
            kind=trace.SpanKind.INTERNAL,
            record_exception=False,
            set_status_on_exception=False,
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
                "gen_ai.tool.call.arguments": json.dumps(args, sort_keys=True),
                "gen_ai.agent.name": SERVICE_NAME,
            },
        ) as span:
            try:
                yield span
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("error.type", type(exc).__name__)
                raise
