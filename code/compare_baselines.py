"""Run a TF-IDF + logistic regression baseline and audit Devign split overlap.

The decision threshold is chosen on validation by F1 and then frozen for test.
No test labels are used to fit the vectorizer, estimator, or threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score, average_precision_score
from sklearn.pipeline import Pipeline

from data_utils import load_records


def score_split(model: Pipeline, path: Path) -> pd.DataFrame:
    rows = load_records(path)
    texts = [row["func"] for row in rows]
    labels = np.asarray([int(row["target"]) for row in rows])
    scores = model.predict_proba(texts)[:, 1]
    return pd.DataFrame({
        "idx": [row.get("idx", i) for i, row in enumerate(rows)],
        "project": [row.get("project", "") for row in rows],
        "commit_id": [row.get("commit_id", "") for row in rows],
        "label": labels,
        "probability": scores,
    })


def best_f1_threshold(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    f1 = 2 * precision[:-1] * recall[:-1] / (precision[:-1] + recall[:-1] + 1e-12)
    best = int(np.argmax(f1))
    return float(thresholds[best]), float(f1[best])


def metrics(frame: pd.DataFrame, threshold: float) -> dict:
    y = frame["label"].to_numpy()
    s = frame["probability"].to_numpy()
    pred = (s >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, s)),
        "pr_auc": float(average_precision_score(y, s)),
        "threshold": float(threshold),
        "sample_count": int(len(y)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def audit_splits(paths: dict[str, Path]) -> dict:
    records = {name: load_records(path) for name, path in paths.items()}
    functions: dict[str, set[str]] = {}
    projects: dict[str, set[str]] = {}
    function_counts: dict[str, dict[str, list[dict]]] = {}
    for split, rows in records.items():
        keys = [hashlib.sha256(row["func"].encode("utf-8")).hexdigest() for row in rows]
        functions[split] = set(keys)
        grouped: dict[str, list[dict]] = {}
        for key, row in zip(keys, rows):
            grouped.setdefault(key, []).append(row)
        function_counts[split] = grouped
        projects[split] = {str(row.get("project", "")) for row in rows if row.get("project")}
    overlap = {}
    names = list(records)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            shared_hashes = functions[left] & functions[right]
            conflicting_hashes = [
                key for key in shared_hashes
                if {int(row["target"]) for row in function_counts[left][key]}
                != {int(row["target"]) for row in function_counts[right][key]}
            ]
            overlap[f"{left}__{right}"] = {
                "exact_function_hash_overlap": len(shared_hashes),
                "label_conflict_hash_count": len(conflicting_hashes),
                "project_overlap_count": len(projects[left] & projects[right]),
                "projects_in_both": sorted(projects[left] & projects[right]),
            }
    duplicates = {
        split: {
            "rows": len(records[split]),
            "unique_function_hashes": len(functions[split]),
            "duplicate_rows_within_split": len(records[split]) - len(functions[split]),
        }
        for split in names
    }
    return {"duplicates": duplicates, "cross_split_overlap": overlap}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="data/devign/train.jsonl")
    parser.add_argument("--validation", default="data/devign/valid.jsonl")
    parser.add_argument("--test", default="data/devign/test.jsonl")
    parser.add_argument("--output-dir", default="results/devign_baseline")
    args = parser.parse_args()
    train_path, valid_path, test_path = map(Path, (args.train, args.validation, args.test))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    train_rows = load_records(train_path)
    x_train = [row["func"] for row in train_rows]
    y_train = np.asarray([int(row["target"]) for row in train_rows])
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="word", token_pattern=r"(?u)\b\w+\b", ngram_range=(1, 2),
            max_features=200_000, min_df=2, sublinear_tf=True, dtype=np.float32,
        )),
        ("classifier", LogisticRegression(max_iter=1000, solver="liblinear", random_state=42)),
    ])
    pipeline.fit(x_train, y_train)

    validation = score_split(pipeline, valid_path)
    threshold, val_best_f1 = best_f1_threshold(validation["label"].to_numpy(), validation["probability"].to_numpy())
    test = score_split(pipeline, test_path)
    validation_metrics = metrics(validation, threshold)
    validation_metrics["best_f1_on_validation"] = val_best_f1
    test_metrics = metrics(test, threshold)
    validation["prediction"] = (validation["probability"] >= threshold).astype(int)
    test["prediction"] = (test["probability"] >= threshold).astype(int)

    validation.to_csv(output / "validation_predictions.csv", index=False)
    test.to_csv(output / "test_predictions.csv", index=False)
    test.loc[test["label"] != test["prediction"], ["idx", "project", "commit_id", "label", "prediction", "probability"]].to_csv(output / "test_errors.csv", index=False)
    (output / "baseline_metrics.json").write_text(json.dumps({
        "model": "TF-IDF word unigrams/bigrams + Logistic Regression",
        "threshold_selected_on": "validation",
        "threshold": threshold,
        "validation": validation_metrics,
        "test": test_metrics,
        "split_audit": audit_splits({"train": train_path, "validation": valid_path, "test": test_path}),
        "parameters": {
            "max_features": 200000, "ngram_range": [1, 2], "min_df": 2,
            "sublinear_tf": True, "classifier": "LogisticRegression(solver=liblinear, max_iter=1000, random_state=42)"
        }
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"threshold": threshold, "validation": validation_metrics, "test": test_metrics,
                      "split_audit": audit_splits({"train": train_path, "validation": valid_path, "test": test_path})},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
