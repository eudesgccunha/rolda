"""Each entry point must really start when run as a program.

Calling ``main()`` from a test does not prove that ``python -m ...`` does
anything: a missing ``if __name__ == "__main__"`` guard makes the module exit
successfully without running. These tests run the real command.
"""

import os
import subprocess
import sys

import pytest

COMMANDS = [
    (["-m", "rolda.entrypoints"], 2, "POSTGRES_USER"),
    (["-m", "rolda.entrypoints.api_main"], 2, "POSTGRES_USER"),
    (["-m", "rolda.entrypoints.migrate"], 2, "POSTGRES_USER"),
    (
        ["-m", "rolda.entrypoints.cli", "label", "t", "span_error", "failure"],
        2,
        "POSTGRES_USER",
    ),
]


def _clean_env() -> dict[str, str]:
    drop = {
        "CLICKHOUSE_USER",
        "CLICKHOUSE_PASSWORD",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "ROLDA_API_TOKEN",
    }
    return {k: v for k, v in os.environ.items() if k not in drop}


@pytest.mark.parametrize(("args", "code", "variable"), COMMANDS)
def test_the_command_runs_and_reports_a_missing_variable(
    args: list[str], code: int, variable: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [sys.executable, *args],
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == code, result.stdout + result.stderr
    assert variable in result.stderr
    assert "Traceback" not in result.stderr
