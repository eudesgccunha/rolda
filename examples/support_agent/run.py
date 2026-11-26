"""Send simulated support-agent sessions to an OTLP/HTTP collector."""

import argparse
import time
from collections import Counter
from datetime import UTC, datetime
from random import Random

from agent import SupportAgent, build_session, setup_tracing

DEFAULT_ENDPOINT = "http://127.0.0.1:4318/v1/traces"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--min-gap", type=float, default=0.2)
    parser.add_argument("--max-gap", type=float, default=1.5)
    args = parser.parse_args()

    rng = Random(args.seed)  # noqa: S311 - seeded simulation, not crypto
    provider, exporter = setup_tracing(args.endpoint)
    agent = SupportAgent(rng, provider.get_tracer("support_agent"))
    kinds: Counter[str] = Counter()
    failed_sessions = 0
    tool_calls = 0
    started = datetime.now(UTC)
    print(f"start {started:%Y-%m-%d %H:%M:%S}Z sessions={args.sessions}")

    for number in range(1, args.sessions + 1):
        outcome = agent.handle(build_session(rng))
        kinds[outcome.fault] += 1
        tool_calls += outcome.tool_calls
        failed_sessions += outcome.failed
        if number % 25 == 0:
            print(f"  {number}/{args.sessions} sessions done")
        time.sleep(rng.uniform(args.min_gap, args.max_gap))

    provider.force_flush()
    provider.shutdown()
    ended = datetime.now(UTC)

    print(f"end   {ended:%Y-%m-%d %H:%M:%S}Z")
    print("fault kinds injected:")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind:16} {count}")
    print(f"sessions ended by a tool error: {failed_sessions}")
    print(f"tool calls: {tool_calls}")
    print(f"export batches ok={exporter.ok} failed={exporter.failed}")


if __name__ == "__main__":
    main()
