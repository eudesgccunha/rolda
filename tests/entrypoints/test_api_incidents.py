"""Tests for the incident endpoints."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import FastAPI

from api_support import ApiClient
from rolda.detection import Confidence
from rolda.entrypoints.api import create_app
from rolda.evals import parse_line
from rolda.incidents import (
    Incident,
    InMemoryIncidentStore,
    InMemoryLabelStore,
    Label,
    LabelSource,
)
from rolda.judge import Verdict
from rolda.traces import InMemorySpanSource, Operation, Span, SpanStatus

ServeApp = Callable[[FastAPI, str | None], ApiClient]
TOKEN = "a-long-enough-test-token"  # noqa: S105 - fake token for tests
SpanFactory = Callable[..., Span]


def _incident(
    trace_id: str, minute: int, rule: str = "span_error", agent: str = "a"
) -> Incident:
    return Incident(
        trace_id=trace_id,
        rule=rule,
        span_id="tool",
        evidence="span 'tool' failed: boom",
        confidence=Confidence.HIGH,
        signature=f"{agent}|{rule}|tool|boom",
        path=("root", "tool"),
        detected_at=datetime(2026, 11, 26, 10, minute, tzinfo=UTC),
    )


def _world(
    make_span: SpanFactory,
) -> tuple[FastAPI, InMemoryLabelStore]:
    incidents = InMemoryIncidentStore()
    for incident in (
        _incident("t1", 1),
        _incident("t2", 2, "tool_loop", "b"),
        _incident("t3", 3),
    ):
        asyncio.run(incidents.save(incident))
    labels = InMemoryLabelStore(incidents)
    asyncio.run(
        labels.upsert(
            Label(
                trace_id="t3",
                rule="span_error",
                source=LabelSource.HUMAN,
                verdict=Verdict.FAILURE,
                reason="real",
                labeler="ana",
                labeled_at=datetime(2026, 11, 26, 12, tzinfo=UTC),
            )
        )
    )
    spans = InMemorySpanSource(
        [
            make_span("root", trace_id="t3", operation=Operation.AGENT),
            make_span(
                "tool",
                trace_id="t3",
                parent="root",
                operation=Operation.TOOL,
                start_s=1,
                status=SpanStatus.ERROR,
                tool_name="search",
                tool_arguments="SECRET ARGUMENTS",
            ),
        ]
    )
    app = create_app(
        incidents=incidents, labels=labels, spans=spans, token=TOKEN
    )
    return app, labels


def test_list_is_newest_first(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    body = client.call("GET", "/incidents").json()

    assert [i["trace_id"] for i in body["items"]] == ["t3", "t2", "t1"]
    assert body["next_cursor"] is None
    first = body["items"][0]
    assert first["rule"] == "span_error"
    assert first["agent"] == "a"
    assert first["path"] == ["root", "tool"]


def test_list_filters_by_rule_and_agent(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    by_rule = client.call("GET", "/incidents?rule=tool_loop").json()
    by_agent = client.call("GET", "/incidents?agent=b").json()

    assert [i["trace_id"] for i in by_rule["items"]] == ["t2"]
    assert [i["trace_id"] for i in by_agent["items"]] == ["t2"]


def test_list_pages_with_a_cursor(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    first = client.call("GET", "/incidents?limit=2").json()
    cursor = quote(first["next_cursor"])
    second = client.call("GET", f"/incidents?limit=2&cursor={cursor}").json()

    assert [i["trace_id"] for i in first["items"]] == ["t3", "t2"]
    assert [i["trace_id"] for i in second["items"]] == ["t1"]
    assert second["next_cursor"] is None


def test_bad_query_values_are_rejected(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    for query in (
        "limit=0",
        "limit=1000",
        "limit=abc",
        "rule=DROP TABLE",
        "cursor=not-a-cursor",
        f"agent={'x' * 500}",
    ):
        reply = client.call("GET", "/incidents?" + quote(query, safe="=&"))
        assert reply.status in (400, 422), query


def test_detail_has_incidents_and_labels(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    body = client.call("GET", "/incidents/t3").json()

    assert body["trace_id"] == "t3"
    [incident] = body["incidents"]
    assert incident["signature"] == "a|span_error|tool|boom"
    [label] = body["labels"]
    assert (label["source"], label["verdict"]) == ("human", "failure")


def test_unknown_trace_is_404(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    assert client.call("GET", "/incidents/ghost").status == 404
    assert client.call("GET", "/incidents/ghost/trace").status == 404


def test_trace_shows_behavior_but_no_tool_arguments(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    reply = client.call("GET", "/incidents/t3/trace")

    body = reply.json()
    assert [s["span_id"] for s in body["spans"]] == ["root", "tool"]
    assert body["spans"][1]["tool"] == "search"
    assert body["spans"][1]["status"] == "error"
    assert "SECRET" not in reply.text


def test_hostile_text_stays_json_data(serve_app: ServeApp) -> None:
    incidents = InMemoryIncidentStore()
    hostile = '</script><img src=x onerror=alert(1)> "quoted"'
    incident = Incident(
        trace_id="t9",
        rule="span_error",
        span_id="s",
        evidence=hostile,
        confidence=Confidence.HIGH,
        signature="a|span_error|tool|x",
        path=("root", hostile),
        detected_at=datetime(2026, 11, 26, 10, tzinfo=UTC),
    )
    asyncio.run(incidents.save(incident))
    app = create_app(
        incidents=incidents,
        labels=InMemoryLabelStore(incidents),
        spans=InMemorySpanSource(),
        token=TOKEN,
    )
    client = serve_app(app, TOKEN)

    reply = client.call("GET", "/incidents/t9")

    assert reply.headers["content-type"].startswith("application/json")
    assert reply.json()["incidents"][0]["evidence"] == hostile


def test_put_label_stores_a_human_label(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    app, labels = _world(make_span)
    client = serve_app(app, TOKEN)

    reply = client.call(
        "PUT",
        "/incidents/t1/span_error/label",
        body={
            "verdict": "false_alarm",
            "reason": "expected",
            "labeler": "ana",
        },
    )

    assert reply.status == 200
    assert reply.json()["verdict"] == "false_alarm"
    stored = asyncio.run(labels.for_trace("t1"))
    assert [(x.source, x.verdict, x.labeler) for x in stored] == [
        (LabelSource.HUMAN, Verdict.FALSE_ALARM, "ana")
    ]


def test_put_label_for_a_missing_incident_is_404(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    reply = client.call(
        "PUT",
        "/incidents/ghost/span_error/label",
        body={"verdict": "failure", "reason": "", "labeler": "ana"},
    )

    assert reply.status == 404


def test_put_label_validates_the_body(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)
    path = "/incidents/t1/span_error/label"
    good = {"verdict": "failure", "reason": "r", "labeler": "ana"}

    bad_bodies = [
        {**good, "verdict": "maybe"},
        {**good, "labeler": ""},
        {**good, "labeler": "x" * 100},
        {**good, "reason": "x" * 1000},
        {**good, "extra": "field"},
        {"verdict": "failure"},
    ]

    for body in bad_bodies:
        assert client.call("PUT", path, body=body).status == 422, body


def test_put_label_needs_the_token(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    reply = client.call(
        "PUT",
        "/incidents/t1/span_error/label",
        body={"verdict": "failure", "reason": "", "labeler": "ana"},
        send_token=False,
    )

    assert reply.status == 401


def test_other_methods_cannot_change_incidents(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    for method in ("POST", "DELETE", "PATCH", "PUT"):
        reply = client.call(method, "/incidents/t1")
        assert reply.status in (404, 405), method


def test_export_returns_the_eval_file(
    serve_app: ServeApp, make_span: SpanFactory
) -> None:
    client = serve_app(_world(make_span)[0], TOKEN)

    reply = client.call("GET", "/evals/export")

    assert reply.status == 200
    assert reply.headers["content-type"].startswith("application/x-ndjson")
    assert "attachment" in reply.headers["content-disposition"]
    [line] = reply.text.splitlines()
    case = parse_line(line)
    assert (case.trace_id, case.expected) == ("t3", "incident")
    assert "SECRET" not in reply.text
