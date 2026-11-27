"""Build eval cases from human-labeled incidents."""

from rolda.evals.case import EvalCase, EvalSpan
from rolda.incidents import LabelStore
from rolda.incidents.labels import LabelSource
from rolda.judge import Verdict
from rolda.traces import Span, SpanSource

_EXPECTED = {
    Verdict.FAILURE: "incident",
    Verdict.FALSE_ALARM: "no_incident",
}


def _eval_span(span: Span) -> EvalSpan:
    return EvalSpan(
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        operation=span.operation.value,
        tool=span.tool_name,
        status=span.status.value,
        input_tokens=span.input_tokens,
        output_tokens=span.output_tokens,
        duration_ns=span.duration_ns,
    )


async def build_cases(labels: LabelStore, spans: SpanSource) -> list[EvalCase]:
    """Return one case per human label that is a failure or a false alarm.

    Uncertain labels are left out. Traces whose spans are gone are skipped.
    """
    cases: list[EvalCase] = []
    for incident, label in await labels.labeled(LabelSource.HUMAN):
        expected = _EXPECTED.get(label.verdict)
        if expected is None:
            continue
        trace_spans = await spans.spans_for_trace(incident.trace_id)
        if not trace_spans:
            continue
        ordered = sorted(trace_spans, key=lambda s: s.started_at)
        cases.append(
            EvalCase(
                trace_id=incident.trace_id,
                rule=incident.rule,
                signature=incident.signature,
                label=label.verdict.value,
                expected=expected,
                spans=tuple(_eval_span(s) for s in ordered),
            )
        )
    return cases
