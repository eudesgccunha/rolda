"""HTTP API: read incidents, label them, export evals.

Every route except ``/health`` needs the bearer token. Trace content is
returned only as JSON data. The API never writes anything but labels.
"""

import base64
import binascii
import hmac
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Path
from fastapi import Query as QueryParam
from pydantic import BaseModel

from rolda.incidents import (
    Incident,
    IncidentStore,
    Label,
    LabelStore,
    OrderKey,
    agent_of,
    order_key,
)
from rolda.traces import Span, SpanSource

MIN_TOKEN_LENGTH = 16
MAX_LIMIT = 200

TraceId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class IncidentOut(BaseModel):
    """An incident as the API shows it."""

    trace_id: str
    rule: str
    agent: str
    span_id: str
    evidence: str
    confidence: str
    signature: str
    path: list[str]
    detected_at: datetime


class LabelOut(BaseModel):
    """A label as the API shows it."""

    trace_id: str
    rule: str
    source: str
    verdict: str
    reason: str
    labeler: str
    labeled_at: datetime


class IncidentPage(BaseModel):
    """One page of incidents, newest first."""

    items: list[IncidentOut]
    next_cursor: str | None


class IncidentDetail(BaseModel):
    """Everything known about the incidents of one trace."""

    trace_id: str
    incidents: list[IncidentOut]
    labels: list[LabelOut]


class SpanOut(BaseModel):
    """The behavior of one span. No prompt, response or arguments."""

    span_id: str
    parent_span_id: str | None
    name: str
    operation: str
    tool: str | None
    status: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ns: int
    started_at: datetime


class TraceOut(BaseModel):
    """The spans of one trace."""

    trace_id: str
    spans: list[SpanOut]


def _incident_out(incident: Incident) -> IncidentOut:
    return IncidentOut(
        trace_id=incident.trace_id,
        rule=incident.rule,
        agent=agent_of(incident),
        span_id=incident.span_id,
        evidence=incident.evidence,
        confidence=incident.confidence.value,
        signature=incident.signature,
        path=list(incident.path),
        detected_at=incident.detected_at,
    )


def _label_out(label: Label) -> LabelOut:
    return LabelOut(
        trace_id=label.trace_id,
        rule=label.rule,
        source=label.source.value,
        verdict=label.verdict.value,
        reason=label.reason,
        labeler=label.labeler,
        labeled_at=label.labeled_at,
    )


def _span_out(span: Span) -> SpanOut:
    return SpanOut(
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        operation=span.operation.value,
        tool=span.tool_name,
        status=span.status.value,
        input_tokens=span.input_tokens,
        output_tokens=span.output_tokens,
        duration_ns=span.duration_ns,
        started_at=span.started_at,
    )


def encode_cursor(key: OrderKey) -> str:
    """Pack an ``OrderKey`` into an opaque URL-safe string."""
    raw = json.dumps([key[0].isoformat(), key[1], key[2]])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> OrderKey:
    """Unpack a cursor. Raise ``ValueError`` if it is not valid."""
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        when, trace_id, rule = data
        if not all(isinstance(x, str) for x in data):
            raise ValueError
        moment = datetime.fromisoformat(when)
    except (ValueError, TypeError, binascii.Error) as exc:
        msg = "invalid cursor"
        raise ValueError(msg) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (moment, trace_id, rule)


def _bearer_check(expected: str) -> Callable[..., Awaitable[None]]:
    async def check(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        supplied = ""
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(
                status_code=401,
                detail="invalid or missing token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return check


def create_app(  # noqa: C901 - one function wires all routes
    *,
    incidents: IncidentStore,
    labels: LabelStore,
    spans: SpanSource,
    token: str,
    docs: bool = False,
) -> FastAPI:
    """Build the API around the given stores and bearer token."""
    if len(token) < MIN_TOKEN_LENGTH:
        msg = f"token must have at least {MIN_TOKEN_LENGTH} characters"
        raise ValueError(msg)
    app = FastAPI(
        title="Rolda",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    protected = APIRouter(dependencies=[Depends(_bearer_check(token))])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @protected.get("/incidents")
    async def list_incidents(
        rule: Annotated[
            str | None, QueryParam(pattern=r"^[a-z_]{1,64}$")
        ] = None,
        agent: Annotated[str | None, QueryParam(max_length=128)] = None,
        limit: Annotated[int, QueryParam(ge=1, le=MAX_LIMIT)] = 50,
        cursor: Annotated[str | None, QueryParam(max_length=512)] = None,
    ) -> IncidentPage:
        after: OrderKey | None = None
        if cursor is not None:
            try:
                after = decode_cursor(cursor)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid cursor"
                ) from exc
        found = await incidents.list(
            rule=rule, agent=agent, limit=limit + 1, after=after
        )
        page = list(found[:limit])
        more = len(found) > limit
        return IncidentPage(
            items=[_incident_out(i) for i in page],
            next_cursor=encode_cursor(order_key(page[-1])) if more else None,
        )

    @protected.get("/incidents/{trace_id}")
    async def incident_detail(trace_id: TraceId) -> IncidentDetail:
        found = await incidents.for_trace(trace_id)
        if not found:
            raise HTTPException(status_code=404, detail="no such trace")
        return IncidentDetail(
            trace_id=trace_id,
            incidents=[_incident_out(i) for i in found],
            labels=[_label_out(x) for x in await labels.for_trace(trace_id)],
        )

    @protected.get("/incidents/{trace_id}/trace")
    async def incident_trace(trace_id: TraceId) -> TraceOut:
        if not await incidents.for_trace(trace_id):
            raise HTTPException(status_code=404, detail="no such trace")
        found = await spans.spans_for_trace(trace_id)
        ordered = sorted(found, key=lambda s: s.started_at)
        return TraceOut(
            trace_id=trace_id, spans=[_span_out(s) for s in ordered]
        )

    app.include_router(protected)
    return app
