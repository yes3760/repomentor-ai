"""Taint analysis package: can user-controlled input reach a dangerous call?

The pattern rules in `security_analyzer` see `eval(x)` and say "potential risk".
This module follows the *data*: it marks values that come from the user
(sources), propagates that mark through assignments, string building and
function calls, and reports a confirmed flow when a marked value reaches a
dangerous call (sink).

Design, in short:
* Flow-sensitive at the top level of a function (re-assignment clears the
  mark), conservative inside branches and loops (marks are only added).
* Inter-procedural through function summaries computed to a fixed point:
  "parameter n reaches sink k", "parameter n flows to the return value",
  "the function returns user input on its own".
* Precision over recall. Constructors of the project's own classes are not
  tracked field by field, URLs with a fixed host are not SSRF, typed
  FastAPI parameters (`int`, `float`, …) are validated, and a list of
  sanitisers (`int()`, `shlex.quote()`, `html.escape()`, …) clears the mark.
  A missed flow costs less user trust than a wrong one.
"""

from repomentor.analyzer.taint.engine import KIND_LABELS, TaintEngine, describe, find_taint_flows
from repomentor.analyzer.taint.sources import call_name, source_of

__all__ = ["KIND_LABELS", "TaintEngine", "call_name", "describe", "find_taint_flows", "source_of"]
