"""Command line: label incidents and export evals."""

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from rolda.evals import (
    EvalCase,
    EvalFormatError,
    build_cases,
    parse_line,
    to_line,
)
from rolda.incidents import (
    Label,
    LabelSource,
    LabelStore,
    UnknownIncidentError,
)
from rolda.judge import Judge, Verdict
from rolda.judge.evaluate import (
    DEFAULT_MIN_CASES,
    InsufficientCasesError,
    evaluate_judge,
)
from rolda.traces import SpanSource


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rolda")
    commands = parser.add_subparsers(dest="command", required=True)
    label = commands.add_parser("label", help="label an incident")
    label.add_argument("trace_id")
    label.add_argument("rule")
    label.add_argument("verdict", choices=[v.value for v in Verdict])
    label.add_argument("--reason", default="")
    label.add_argument("--labeler", default="cli")
    export = commands.add_parser(
        "export-evals", help="export labeled incidents as JSONL"
    )
    export.add_argument("--out", required=True, type=Path)
    export.add_argument("--force", action="store_true")
    judge_eval = commands.add_parser(
        "judge-eval", help="measure judge agreement with human labels"
    )
    judge_eval.add_argument("--evals", required=True, type=Path)
    judge_eval.add_argument("--min-cases", type=int, default=DEFAULT_MIN_CASES)
    return parser


class _MissingKeyError(RuntimeError):
    pass


def _default_judge() -> Judge:
    from rolda.adapters.anthropic_judge import DEFAULT_MODEL, AnthropicJudge

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        msg = "ANTHROPIC_API_KEY is not set"
        raise _MissingKeyError(msg)
    return AnthropicJudge(
        key, model=os.environ.get("ROLDA_JUDGE_MODEL", DEFAULT_MODEL)
    )


def _read_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        try:
            cases.append(parse_line(line))
        except EvalFormatError as exc:
            msg = f"{path} line {number}: {exc}"
            raise EvalFormatError(msg) from exc
    return cases


def _judge_eval(args: argparse.Namespace, judge: Judge | None) -> int:
    try:
        cases = _read_cases(args.evals)
        report = asyncio.run(
            evaluate_judge(
                judge or _default_judge(), cases, min_cases=args.min_cases
            )
        )
    except (EvalFormatError, InsufficientCasesError, _MissingKeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"kappa: {report.kappa:.3f}")
    print(f"agreement: {report.agreement:.3f}")
    print(f"scored: {report.scored}")
    print(f"uncertain: {report.uncertain}")
    for (human, machine), count in sorted(report.confusion.items()):
        print(f"human={human} judge={machine}: {count}")
    return 0


def _default_label_store() -> LabelStore:
    from rolda.adapters.postgres import PostgresLabelStore
    from rolda.entrypoints.settings import load_settings

    return PostgresLabelStore(load_settings(os.environ).postgres_dsn)


def _default_span_source() -> SpanSource:
    from rolda.adapters.clickhouse import ClickHouseSpanSource
    from rolda.entrypoints.settings import load_settings

    return ClickHouseSpanSource(load_settings(os.environ))


def _label(
    args: argparse.Namespace,
    store: LabelStore | None,
    clock: Callable[[], datetime],
) -> int:
    label = Label(
        trace_id=args.trace_id,
        rule=args.rule,
        source=LabelSource.HUMAN,
        verdict=Verdict(args.verdict),
        reason=args.reason,
        labeler=args.labeler,
        labeled_at=clock(),
    )
    try:
        asyncio.run((store or _default_label_store()).upsert(label))
    except UnknownIncidentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"labeled {label.trace_id} {label.rule}: {args.verdict}")
    return 0


def _write_private(path: Path, text: str, *, force: bool) -> None:
    """Write a file readable by its owner only; refuse to overwrite."""
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if force else os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(text)


def _export(
    args: argparse.Namespace,
    store: LabelStore | None,
    spans: SpanSource | None,
) -> int:
    cases = asyncio.run(
        build_cases(
            store or _default_label_store(),
            spans or _default_span_source(),
        )
    )
    text = "".join(to_line(case) + "\n" for case in cases)
    try:
        _write_private(args.out, text, force=args.force)
    except FileExistsError:
        print(
            f"error: {args.out} exists; use --force to overwrite",
            file=sys.stderr,
        )
        return 1
    print(f"exported {len(cases)} cases to {args.out}")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    label_store: LabelStore | None = None,
    span_source: SpanSource | None = None,
    judge: Judge | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> int:
    """Run one command. Return the process exit code."""
    args = _parser().parse_args(argv)
    if args.command == "label":
        return _label(args, label_store, clock)
    if args.command == "judge-eval":
        return _judge_eval(args, judge)
    return _export(args, label_store, span_source)


if __name__ == "__main__":
    sys.exit(main())
