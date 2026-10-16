"""Train/test leakage and pandas anti-patterns."""

import pytest

from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.ml_analyzer import analyze_data_science
from tests.conftest import EXAMPLES, analyze


def findings(make_project, code: str) -> list[tuple[str, int]]:
    root = make_project({"model.py": code})
    report, _ = analyze_data_science(scan_project(root), True)
    return [(f.rule, f.line) for f in report.findings]


def test_ml_example_findings():
    result = analyze(EXAMPLES / "ml_project", check_dependencies=False)
    rules = {f.rule for f in result.data_science.findings}
    assert rules == {"LEAK001", "LEAK002", "PD001", "PD002", "PD003", "PD004", "PD005", "PD006"}
    leak = next(f for f in result.data_science.findings if f.rule == "LEAK001")
    assert (leak.file, leak.line) == ("src/train.py", 18) and "X_scaled" in leak.detail
    assert any(f.label.startswith("Veri sızıntısı") for f in result.score.category("quality").factors)


@pytest.mark.parametrize(("code", "expected"), [
    ("from imblearn.over_sampling import SMOTE\nfrom sklearn.model_selection import train_test_split\n"
     "X_res, y_res = SMOTE().fit_resample(X, y)\na, b, c, d = train_test_split(X_res, y_res)\n", [("LEAK001", 3)]),
    ("from sklearn.preprocessing import StandardScaler\nfrom sklearn.model_selection import cross_val_score\n"
     "X = StandardScaler().fit_transform(X)\ncross_val_score(model, X, y, cv=5)\n", [("LEAK001", 3)]),
    ("imp = SimpleImputer()\nimp.fit(X)\nX2 = imp.transform(X)\nsearch = GridSearchCV(model, grid)\nsearch.fit(X2, y)\n", [("LEAK001", 2)]),
    # both lines learn from validation data: the vectoriser vocabulary and the model
    ("vec = TfidfVectorizer()\nX_val = vec.fit_transform(texts_val)\nm.fit(x_val, y_val)\n", [("LEAK002", 2), ("LEAK002", 3)]),
])
def test_leakage_variants(make_project, code, expected):
    assert findings(make_project, code) == expected


@pytest.mark.parametrize("code", [
    # split first, then fit on the training part only
    "X_tr, X_te, y_tr, y_te = train_test_split(X, y)\ns = StandardScaler()\nX_tr = s.fit_transform(X_tr)\nX_te = s.transform(X_te)\n",
    # the recommended fix
    "pipe = make_pipeline(StandardScaler(), LogisticRegression())\ncross_val_score(pipe, X, y)\n",
    # a model fitted on all data and never split is not leakage (it is just not evaluated)
    "model = LogisticRegression()\nmodel.fit(X, y)\n",
    # 'latest' is not test data
    "latest = load()\nmodel.fit(latest, y)\n",
])
def test_correct_ml_code_is_not_flagged(make_project, code):
    assert findings(make_project, code) == []


@pytest.mark.parametrize("code", [
    "data = []\nfor x in items:\n    data.append(x)\n",                       # a list named like a frame
    "config = {}\nconfig['model']['params'] = {'C': 1}\n",                      # nested dict, not chained indexing
    "df = pd.read_csv('a.csv')\ndf.loc[df['a'] > 1, 'b'] = 0\n",                # the correct single-step assignment
    "df = pd.read_csv('a.csv')\ndf['c'] = df['a'] * df['b']\n",                 # vectorised column maths
])
def test_correct_pandas_code_is_not_flagged(make_project, code):
    assert findings(make_project, code) == []


def test_frames_are_recognised_by_construction_and_convention(make_project):
    code = (
        "import pandas as pd\n"
        "customers = pd.read_csv('c.csv')\n"
        "customers = customers.dropna()\n"
        "customers['vip'][customers['spend'] > 100] = True\n"
        "def report(sales_df):\n    return sales_df.append(sales_df.iloc[0])\n"
    )
    assert findings(make_project, code) == [("PD003", 4), ("PD004", 6)]


def test_checks_only_run_for_data_projects(make_project):
    root = make_project({"app.py": "for _, row in df.iterrows():\n    pass\n"})
    report, issues = analyze_data_science(scan_project(root), False)
    assert not report.applicable and report.findings == [] and issues == []


def test_medium_example_row_wise_apply(medium_result):
    assert [f.rule for f in medium_result.data_science.findings] == ["PD002"]
