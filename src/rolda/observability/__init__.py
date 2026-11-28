"""A tiny metrics registry that renders the Prometheus text format.

It has no dependency. Counters and gauges only, which is all the worker needs.
"""

from datetime import UTC, datetime

_Labels = tuple[tuple[str, str], ...]


def _key(labels: dict[str, str] | None) -> _Labels:
    return tuple(sorted((labels or {}).items()))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(value)


class Metrics:
    """Counters and gauges for one process, plus a liveness timestamp."""

    def __init__(self) -> None:
        self._kind: dict[str, str] = {}
        self._help: dict[str, str] = {}
        self._values: dict[str, dict[_Labels, float]] = {}
        self._last_iteration: datetime | None = None

    def describe(self, name: str, kind: str, help_text: str) -> None:
        """Declare a metric. ``kind`` is ``counter`` or ``gauge``."""
        self._kind[name] = kind
        self._help[name] = help_text
        self._values.setdefault(name, {})

    def inc(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        value: float = 1,
    ) -> None:
        """Add to a counter."""
        series = self._values[name]
        key = _key(labels)
        series[key] = series.get(key, 0) + value

    def set(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Set a gauge."""
        self._values[name][_key(labels)] = value

    def touch(self, when: datetime | None = None) -> None:
        """Record that the main loop is alive."""
        self._last_iteration = when or datetime.now(UTC)

    @property
    def last_iteration(self) -> datetime | None:
        """When the main loop last ran, or None if it never did."""
        return self._last_iteration

    def render(self) -> str:
        """Return every metric in the Prometheus text format."""
        lines: list[str] = []
        for name in sorted(self._values):
            lines.append(f"# HELP {name} {self._help[name]}")
            lines.append(f"# TYPE {name} {self._kind[name]}")
            for labels, value in sorted(self._values[name].items()):
                if labels:
                    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
                    lines.append(f"{name}{{{inner}}} {_format(value)}")
                else:
                    lines.append(f"{name} {_format(value)}")
        return "\n".join(lines) + "\n"


__all__ = ["Metrics"]
