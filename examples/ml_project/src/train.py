"""Train and compare churn models."""

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features import add_features, load, risk_labels

FEATURES = ["tenure", "monthly_charges", "total_charges", "tenure_years", "long_contract"]


def baseline(path: str) -> float:
    df = add_features(load(path))
    X, y = df[FEATURES], df["churn"]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
    model = LogisticRegression(max_iter=1000).fit(X_train, y_train)
    return model.score(X_test, y_test)


def forest(path: str) -> float:
    df = risk_labels(add_features(load(path)))
    X, y = df[FEATURES], df["churn"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.fit_transform(X_test)
    model = RandomForestClassifier(random_state=42).fit(X_train, y_train)
    return model.score(X_test, y_test)


def cross_validated(path: str) -> float:
    """The correct way: scaling happens inside each fold."""
    df = add_features(load(path))
    pipeline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    config = {"model": {"params": {}}}
    config["model"]["params"] = {"C": 1.0}
    return cross_val_score(pipeline, df[FEATURES], df["churn"], cv=5).mean()


if __name__ == "__main__":
    print(baseline("data/churn.csv"), forest("data/churn.csv"), cross_validated("data/churn.csv"))
