"""Data-science checks: train/test leakage in scikit-learn code and pandas anti-patterns.

Leakage is found by following each scope's statements in source order:
* an estimator that *learns statistics* (scaler, imputer, encoder, vectoriser,
  feature selector, resampler) is fitted on a dataset before that dataset is
  split or cross-validated → the test folds have seen the training statistics;
* anything is fitted on a variable named like test data.
A `Pipeline` / `make_pipeline` is the correct fix and is never flagged.

The pandas rules only look at names that are DataFrames by construction
(`pd.read_csv`, `pd.DataFrame`, frame methods) or by convention (`df`,
`*_df`), so nested dictionaries are not mistaken for chained indexing.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.analyzer.taint.sources import call_name
from repomentor.models.analysis_result import MLFinding, MLReport
from repomentor.models.issue import Issue, Location

LEARNING_TRANSFORMERS = {
    "StandardScaler", "MinMaxScaler", "RobustScaler", "MaxAbsScaler", "Normalizer", "QuantileTransformer",
    "PowerTransformer", "PCA", "TruncatedSVD", "KernelPCA", "SimpleImputer", "KNNImputer", "IterativeImputer",
    "OneHotEncoder", "OrdinalEncoder", "TargetEncoder", "TfidfVectorizer", "CountVectorizer", "SelectKBest",
    "SelectPercentile", "SelectFromModel", "VarianceThreshold", "KBinsDiscretizer", "SMOTE", "ADASYN",
    "RandomOverSampler", "RandomUnderSampler", "TomekLinks", "BorderlineSMOTE",
}
SPLITTERS = {"train_test_split", "cross_val_score", "cross_validate", "cross_val_predict", "learning_curve"}
SEARCH_CV = {"GridSearchCV", "RandomizedSearchCV", "HalvingGridSearchCV", "HalvingRandomSearchCV"}
FIT_METHODS = {"fit", "fit_transform", "fit_resample"}
TEST_NAME = re.compile(r"(^|_)(test|val|valid|validation|holdout)(_|\d*$)|^[xy]test$", re.I)

FRAME_CONSTRUCTORS = {"DataFrame", "read_csv", "read_excel", "read_json", "read_parquet", "read_sql", "read_table",
                      "read_feather", "read_pickle", "concat", "merge", "get_dummies", "pivot_table", "json_normalize"}
FRAME_METHODS = {"copy", "dropna", "fillna", "drop", "drop_duplicates", "merge", "join", "assign", "query", "rename",
                 "reset_index", "set_index", "sort_values", "sort_index", "astype", "replace", "head", "tail", "sample",
                 "apply", "groupby", "agg", "aggregate", "pivot", "melt", "loc", "iloc", "filter", "select_dtypes"}
# Only strong conventions; generic names such as `data` are often lists, so they count only when built by pandas.
FRAME_NAME = re.compile(r"^df\d*$|_df$|^df_", re.I)


@dataclass
class _Scope:
    file: str
    frames: set[str] = field(default_factory=set)
    estimators: dict[str, str] = field(default_factory=dict)     # variable -> class name
    fitted_on_full: dict[str, int] = field(default_factory=dict)  # transformer variable -> fit line
    leaky: dict[str, int] = field(default_factory=dict)           # data variable -> line its statistics leaked
    findings: list[MLFinding] = field(default_factory=list)


def _scopes(tree: ast.Module) -> list[list[ast.stmt]]:
    bodies = [[s for s in tree.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]]
    bodies += [node.body for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return bodies


def _flatten(statements: list[ast.stmt], in_loop: bool = False) -> list[tuple[ast.stmt, bool]]:
    """Simple statements in source order with whether they sit inside a loop (nested defs excluded)."""
    flat: list[tuple[ast.stmt, bool]] = []
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        loop = in_loop or isinstance(statement, (ast.For, ast.AsyncFor, ast.While))
        children = [getattr(statement, name) for name in ("body", "orelse", "finalbody") if isinstance(getattr(statement, name, None), list)]
        children += [handler.body for handler in getattr(statement, "handlers", [])]
        children += [case.body for case in getattr(statement, "cases", [])]
        flat.append((statement, in_loop))
        for child in children:
            flat += _flatten(child, loop)
    return flat


def _names(node: ast.AST | None) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [n for element in node.elts for n in _names(element)]
    return []


def _assigned(statement: ast.stmt) -> list[str]:
    if isinstance(statement, ast.Assign):
        return [n for target in statement.targets for n in _names(target)]
    if isinstance(statement, ast.AnnAssign):
        return _names(statement.target)
    return []


def _own_calls(statement: ast.stmt) -> list[ast.Call]:
    """Calls belonging to this statement itself (not to nested block statements), in source order."""
    roots = [getattr(statement, attr) for attr in ("value", "test", "iter", "items", "subject") if getattr(statement, attr, None) is not None]
    roots = [r for root in roots for r in (root if isinstance(root, list) else [root])]
    calls = [node for root in roots for node in ast.walk(root) if isinstance(node, ast.Call)]
    return sorted(calls, key=lambda c: (c.lineno, c.col_offset))


# --- Leakage -------------------------------------------------------------------------------------------

def _estimator_class(call: ast.Call, scope: _Scope) -> str:
    receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
    if isinstance(receiver, ast.Call):
        return call_name(receiver.func).rsplit(".", 1)[-1]
    if isinstance(receiver, ast.Name):
        return scope.estimators.get(receiver.id, "")
    return ""


def _check_split(call: ast.Call, scope: _Scope, cv_fit: bool) -> None:
    is_split = call_name(call.func).rsplit(".", 1)[-1] == "train_test_split"
    args = call.args if cv_fit or is_split else call.args[1:]       # cross_val_score(estimator, X, y)
    where = "train_test_split'e" if is_split else "çapraz doğrulamaya"
    for name in {n for arg in [*args, *(kw.value for kw in call.keywords)] for n in _names(arg)}:
        if name in scope.leaky:
            scope.findings.append(MLFinding("LEAK001", scope.file, scope.leaky[name],
                                            f"`{name}` tüm veriyle öğrenilen istatistiklerle dönüştürüldü, sonra {where} girdi ({scope.file}:{call.lineno})"))


def _check_fit(call: ast.Call, scope: _Scope, targets: list[str]) -> None:
    method = call.func.attr
    data = _names(call.args[0]) if call.args else []
    estimator = _estimator_class(call, scope)
    if estimator in SEARCH_CV and method == "fit":
        _check_split(call, scope, cv_fit=True)
        return
    if data and TEST_NAME.search(data[0]):
        scope.findings.append(MLFinding("LEAK002", scope.file, call.lineno, f"`{ast.unparse(call)[:80]}`"))
        return
    if estimator not in LEARNING_TRANSFORMERS or not data:
        return
    if isinstance(call.func.value, ast.Name):
        scope.fitted_on_full[call.func.value.id] = call.lineno
    if method != "fit":
        for name in targets:
            scope.leaky[name] = call.lineno


def _track_leakage(call: ast.Call, scope: _Scope, targets: list[str]) -> None:
    short = call_name(call.func).rsplit(".", 1)[-1]
    if short in SPLITTERS:
        _check_split(call, scope, cv_fit=False)
    elif isinstance(call.func, ast.Attribute) and short in FIT_METHODS:
        _check_fit(call, scope, targets)
    elif short == "transform" and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        if (fit_line := scope.fitted_on_full.get(call.func.value.id)) is not None:
            for name in targets:
                scope.leaky[name] = fit_line


def _remember_objects(statement: ast.stmt, scope: _Scope) -> None:
    value = getattr(statement, "value", None)
    if not isinstance(value, ast.Call):
        return
    name = call_name(value.func)
    short = name.rsplit(".", 1)[-1]
    receiver = value.func.value if isinstance(value.func, ast.Attribute) else None
    for target in _assigned(statement):
        if short in LEARNING_TRANSFORMERS | SEARCH_CV | {"Pipeline", "make_pipeline"}:
            scope.estimators[target] = short
        elif short in FRAME_CONSTRUCTORS or (short in FRAME_METHODS and isinstance(receiver, ast.Name) and _is_frame(receiver.id, scope)):
            scope.frames.add(target)


# --- pandas ---------------------------------------------------------------------------------------------

def _is_frame(name: str, scope: _Scope) -> bool:
    return name in scope.frames or bool(FRAME_NAME.search(name))


def _frame_base(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Subscript, ast.Attribute)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _chained_assignment(statement: ast.stmt, scope: _Scope) -> None:
    for target in getattr(statement, "targets", []):
        inner = target.value if isinstance(target, ast.Subscript) else None
        if isinstance(inner, ast.Subscript) and (base := _frame_base(inner)) and _is_frame(base, scope):
            scope.findings.append(MLFinding("PD003", scope.file, statement.lineno, f"`{ast.unparse(target)[:70]} = …`"))


def _pandas_call(call: ast.Call, scope: _Scope, in_loop: bool, targets: list[str]) -> None:
    if not isinstance(call.func, ast.Attribute):
        return
    method, receiver = call.func.attr, _frame_base(call.func.value)
    frame = receiver is not None and _is_frame(receiver, scope)
    axis = next((kw.value for kw in call.keywords if kw.arg == "axis"), None)
    if method == "iterrows":
        scope.findings.append(MLFinding("PD001", scope.file, call.lineno, f"`{receiver}.iterrows()`"))
    elif method == "apply" and isinstance(axis, ast.Constant) and axis.value in {1, "columns"}:
        scope.findings.append(MLFinding("PD002", scope.file, call.lineno, f"`{ast.unparse(call)[:70]}`"))
    elif method == "append" and frame:
        scope.findings.append(MLFinding("PD004", scope.file, call.lineno, f"`{ast.unparse(call)[:70]}`"))
    elif method == "concat" and in_loop and set(targets) & {n for arg in call.args for n in _names_in(arg)}:
        scope.findings.append(MLFinding("PD005", scope.file, call.lineno, f"`{ast.unparse(call)[:70]}`"))


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _row_loop(statement: ast.stmt, scope: _Scope) -> None:
    """`for i in range(len(df)):` reading `df.iloc[i]` / `df.loc[i]` row by row."""
    if not isinstance(statement, ast.For) or not isinstance(statement.iter, ast.Call) or call_name(statement.iter.func) != "range":
        return
    inner = statement.iter.args[-1] if statement.iter.args else None
    if not (isinstance(inner, ast.Call) and call_name(inner.func) == "len" and inner.args and isinstance(inner.args[0], ast.Name)):
        return
    frame = inner.args[0].id
    if not _is_frame(frame, scope):
        return
    row_access = any(isinstance(n, ast.Attribute) and n.attr in {"iloc", "loc", "at", "iat"} and _frame_base(n) == frame
                     for s in statement.body for n in ast.walk(s))
    if row_access:
        scope.findings.append(MLFinding("PD006", scope.file, statement.lineno, f"`for … in range(len({frame}))`"))


# --- driver ------------------------------------------------------------------------------------------------

def _analyse_scope(path: str, statements: list[ast.stmt], params: list[str]) -> list[MLFinding]:
    scope = _Scope(path, frames={p for p in params if FRAME_NAME.search(p)})
    for statement, in_loop in _flatten(statements):
        targets = _assigned(statement)
        _row_loop(statement, scope)
        _chained_assignment(statement, scope)
        for call in _own_calls(statement):
            _track_leakage(call, scope, targets)
            _pandas_call(call, scope, in_loop, targets)
        _remember_objects(statement, scope)
    return scope.findings


def _function_params(tree: ast.Module) -> dict[int, list[str]]:
    return {
        id(node.body): [a.arg for a in node.args.args + node.args.kwonlyargs]
        for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def analyze_data_science(project: ProjectFiles, uses_data_stack: bool) -> tuple[MLReport, list[Issue]]:
    report = MLReport(applicable=uses_data_stack)
    if not uses_data_stack:
        return report, []
    for path, tree in project.parsed_python(include_tests=False):
        params = _function_params(tree)
        for body in _scopes(tree):
            report.findings += _analyse_scope(path, body, params.get(id(body), []))
    unique = {(f.rule, f.file, f.line): f for f in report.findings}
    report.findings = sorted(unique.values(), key=lambda f: (f.rule, f.file, f.line))
    return report, data_science_issues(report)


def data_science_issues(report: MLReport) -> list[Issue]:
    groups: dict[str, list[MLFinding]] = defaultdict(list)
    for finding in report.findings:
        groups[finding.rule].append(finding)
    issues = []
    for rule, findings in groups.items():
        detail = "; ".join(f"{f.file}:{f.line} {f.detail}" for f in findings[:3]) + (f" (+{len(findings) - 3})" if len(findings) > 3 else "")
        issues.append(make_issue(rule, [Location(f.file, f.line) for f in findings][:15], {"count": len(findings), "detail": detail},
                                 source="ast", count=len(findings)))
    return issues
