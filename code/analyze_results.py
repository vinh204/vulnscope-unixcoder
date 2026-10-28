"""Build comparison, split-audit, and error-analysis artifacts for the report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)

from data_utils import load_records


ROOT = Path(__file__).resolve().parents[1]


def evaluate(frame: pd.DataFrame, score_column: str, threshold: float) -> dict:
    labels = frame["label"].to_numpy(dtype=int)
    scores = frame[score_column].to_numpy(dtype=float)
    predictions = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "sample_count": int(len(frame)),
        "threshold": float(threshold),
    }


def main() -> None:
    devign = ROOT / "data" / "devign"
    results = ROOT / "results"
    final = results / "devign_full_ft_cpu_final"
    baseline_path = results / "devign_baseline" / "baseline_metrics.json"
    ux_val_path = final / "validation_metrics.json"
    ux_test_path = final / "test_metrics.json"
    ux_test_pred = pd.read_csv(final / "test_predictions.csv")
    baseline_test_pred = pd.read_csv(results / "devign_baseline" / "test_predictions.csv")
    ux_val = json.loads(ux_val_path.read_text(encoding="utf-8"))
    ux_test_raw = json.loads(ux_test_path.read_text(encoding="utf-8"))
    ux_test = ux_test_raw.get("test_metrics", ux_test_raw)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    ux_threshold = float(ux_val["threshold"])
    baseline_threshold = float(baseline["threshold"])
    comparisons = []
    for name, frame, column, val_threshold in (
        ("UniXcoder fine-tuned", ux_test_pred, "vulnerable_probability", ux_threshold),
        ("TF-IDF + Logistic Regression", baseline_test_pred, "probability", baseline_threshold),
    ):
        tuned = evaluate(frame, column, val_threshold)
        tuned["model"] = name
        tuned["operating_point"] = "threshold selected on validation"
        comparisons.append(tuned)
        fixed = evaluate(frame, column, 0.5)
        fixed["model"] = name
        fixed["operating_point"] = "threshold 0.5"
        comparisons.append(fixed)

    split_rows = {name: load_records(devign / filename) for name, filename in (
        ("train", "train.jsonl"), ("validation", "valid.jsonl"), ("test", "test.jsonl"))}
    hash_func = lambda row: hashlib.sha256(row["func"].encode("utf-8")).hexdigest()
    hash_sets = {name: {hash_func(row) for row in rows} for name, rows in split_rows.items()}
    train_validation_hashes = hash_sets["train"] | hash_sets["validation"]
    duplicate_test_rows = {
        row["idx"] for row in split_rows["test"] if hash_func(row) in train_validation_hashes
    }
    sensitivity = []
    for name, frame, column, val_threshold in (
        ("UniXcoder fine-tuned", ux_test_pred, "vulnerable_probability", ux_threshold),
        ("TF-IDF + Logistic Regression", baseline_test_pred, "probability", baseline_threshold),
    ):
        filtered = frame[~frame["idx"].isin(duplicate_test_rows)]
        result = evaluate(filtered, column, val_threshold)
        result["model"] = name
        result["excluded_exact_test_duplicates"] = len(duplicate_test_rows)
        sensitivity.append(result)

    lookup = {row["idx"]: row for row in split_rows["test"]}
    err = ux_test_pred.copy()
    err["project"] = err["idx"].map(lambda idx: lookup[idx].get("project", ""))
    err["commit_id"] = err["idx"].map(lambda idx: lookup[idx].get("commit_id", ""))
    err["func"] = err["idx"].map(lambda idx: lookup[idx]["func"])
    err["error_type"] = np.select(
        [(err["label"] == 0) & (err["prediction"] == 1),
         (err["label"] == 1) & (err["prediction"] == 0)],
        ["false_positive", "false_negative"], default="correct",
    )
    errors = err[err["error_type"] != "correct"]
    errors[["idx", "project", "commit_id", "label", "prediction", "vulnerable_probability",
            "token_count", "truncated", "error_type"]].to_csv(
        final / "test_error_cases.csv", index=False
    )
    error_summary = {}
    for error_type in ("false_positive", "false_negative"):
        group = errors[errors["error_type"] == error_type]
        error_summary[error_type] = {
            "count": int(len(group)),
            "mean_token_count": float(group["token_count"].mean()),
            "truncated_count": int(group["truncated"].sum()),
            "truncated_fraction": float(group["truncated"].mean()),
            "examples": group.sort_values("vulnerable_probability", ascending=(error_type == "false_negative"))[
                ["idx", "project", "label", "prediction", "vulnerable_probability", "token_count", "truncated"]
            ].head(5).to_dict(orient="records"),
        }

    audit = baseline["split_audit"]
    (results / "devign_split_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results / "model_comparison.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results / "duplicate_sensitivity.json").write_text(
        json.dumps({"test_rows_with_exact_duplicates_in_train_or_validation": sorted(duplicate_test_rows),
                    "results": sensitivity}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (final / "error_analysis.json").write_text(
        json.dumps({"threshold": ux_threshold, "counts": error_summary,
                    "total_truncated_test_functions": int(ux_test_pred["truncated"].sum()),
                    "total_test_functions": int(len(ux_test_pred))},
                   ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metadata = dict(ux_test)
    metadata.update({
        "model": "UniXcoder fine-tuned on Devign train split",
        "base_model": "microsoft/unixcoder-base",
        "training_samples": 21854,
        "epochs": 3,
        "block_size": 512,
        "train_batch_size": 4,
        "gradient_accumulation_steps": 4,
        "effective_batch_size": 16,
        "learning_rate": 2e-5,
        "seed": 42,
        "device": "CPU",
        "checkpoint_selection": "best validation F1 at threshold 0.5 during training",
        "reported_test_threshold": ux_threshold,
        "threshold_selection": "F1 maximized on validation only, then locked before test evaluation",
    })
    ux_test_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model_comparison": comparisons,
                      "duplicate_sensitivity": sensitivity,
                      "error_analysis": error_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
