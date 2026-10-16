"""Values the analysis passes around."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Taint:
    origin: str                  # what produced the value, e.g. "request.args.get('q')"
    line: int
    remote: bool = True          # web input; False for console input (input(), sys.argv)
    hops: tuple[str, ...] = ()   # variables the value passed through
    param: int | None = None     # set while summarising: "comes from parameter #n"

    def via(self, name: str) -> Taint:
        return self if self.hops[-1:] == (name,) else replace(self, hops=(self.hops + (name,))[-6:])


@dataclass
class Summary:
    returns_source: Taint | None = None
    param_returns: set[int] = field(default_factory=set)
    param_sinks: dict[int, tuple[str, str, str, int]] = field(default_factory=dict)  # n -> (kind, sink, file, line)

    def merge(self, other: Summary) -> bool:
        """Union `other` into self; True if anything changed."""
        before = (self.returns_source, set(self.param_returns), dict(self.param_sinks))
        self.returns_source = self.returns_source or other.returns_source
        self.param_returns |= other.param_returns
        for index, sink in other.param_sinks.items():
            self.param_sinks.setdefault(index, sink)
        return before != (self.returns_source, self.param_returns, self.param_sinks)


@dataclass
class _Function:
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Module
    file: str
    name: str
    params: list[ast.arg]
    route: bool = False


