"""Normalization adapter: raw OpenTelemetry rows to domain spans.

This is the only module that reads raw OpenTelemetry attributes. The
GenAI semantic conventions are not stable, so both current and legacy
attribute names are accepted here.
"""

import re
from collections.abc import Mapping
from datetime import UTC, datetime

from rolda.traces.model import Operation, Span, SpanStatus

_OPERATIONS: dict[str, Operation] = {
    "chat": Operation.LLM,
    "text_completion": Operation.LLM,
    "generate_content": Operation.LLM,
    "embeddings": Operation.LLM,
    "execute_tool": Operation.TOOL,
    "invoke_agent": Operation.AGENT,
    "create_agent": Operation.AGENT,
}


class NormalizationError(ValueError):
    """Raised when a raw span row cannot be turned into a ``Span``."""


def normalize_span(row: Mapping[str, object]) -> Span:
    """Convert one raw span row into a domain ``Span``."""
    attributes = _attributes(row.get("SpanAttributes"))
    service = _text(row.get("ServiceName"))
    return Span(
        trace_id=_required(row, "TraceId"),
        span_id=_required(row, "SpanId"),
        parent_span_id=_text(row.get("ParentSpanId")),
        name=_text(row.get("SpanName")) or "",
        agent=attributes.get("gen_ai.agent.name") or service,
        operation=_OPERATIONS.get(
            attributes.get("gen_ai.operation.name", ""), Operation.OTHER
        ),
        started_at=_timestamp(row.get("Timestamp")),
        duration_ns=_non_negative(row.get("Duration")) or 0,
        status=_status(row.get("StatusCode")),
        status_message=_text(row.get("StatusMessage")) or "",
        model=_first(
            attributes, "gen_ai.request.model", "gen_ai.response.model"
        ),
        input_tokens=_non_negative(
            _first(
                attributes,
                "gen_ai.usage.input_tokens",
                "gen_ai.usage.prompt_tokens",
            )
        ),
        output_tokens=_non_negative(
            _first(
                attributes,
                "gen_ai.usage.output_tokens",
                "gen_ai.usage.completion_tokens",
            )
        ),
        tool_name=attributes.get("gen_ai.tool.name"),
        tool_arguments=attributes.get("gen_ai.tool.call.arguments"),
    )


def _attributes(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _required(row: Mapping[str, object], field: str) -> str:
    value = _text(row.get(field))
    if value is None:
        msg = f"missing required field {field}"
        raise NormalizationError(msg)
    return value


def _first(attributes: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        if name in attributes:
            return attributes[name]
    return None


def _non_negative(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(str(value))
    except ValueError:
        return None
    return number if number >= 0 else None


def _status(value: object) -> SpanStatus:
    code = (_text(value) or "").lower()
    if code.endswith("error"):
        return SpanStatus.ERROR
    if code.endswith("ok"):
        return SpanStatus.OK
    return SpanStatus.UNSET


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        if text is None:
            msg = "missing required field Timestamp"
            raise NormalizationError(msg)
        parsed = _parse_iso(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_ISO = re.compile(
    r"^(?P<head>[^.]+)(?:\.(?P<frac>\d+))?(?P<zone>Z|[+-]\d{2}:?\d{2})?$"
)


def _parse_iso(text: str) -> datetime:
    # Python keeps at most microseconds, ClickHouse gives nanoseconds.
    match = _ISO.match(text)
    if match is None:
        msg = f"invalid Timestamp {text!r}"
        raise NormalizationError(msg)
    fraction = (match["frac"] or "")[:6].ljust(6, "0")
    zone = "+00:00" if match["zone"] in (None, "Z") else match["zone"]
    try:
        parsed = datetime.fromisoformat(f"{match['head']}.{fraction}{zone}")
    except ValueError as exc:
        msg = f"invalid Timestamp {text!r}"
        raise NormalizationError(msg) from exc
    return parsed
