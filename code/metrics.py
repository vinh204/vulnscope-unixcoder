"""Evaluation helpers shared by CLI experiments and the dashboard."""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)


def binary_metrics(labels, vulnerable_probabilities, threshold=0.5):
    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(vulnerable_probabilities, dtype=float)
    predictions = (probabilities >= threshold).astype(int)
    result = {
        "accuracy": accuracy_score(labels, predictions),
        "precision": precision_score(labels, predictions, zero_division=0),
        "recall": recall_score(labels, predictions, zero_division=0),
        "f1": f1_score(labels, predictions, zero_division=0),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
        "threshold": float(threshold),
        "roc_auc": roc_auc_score(labels, probabilities) if len(np.unique(labels)) == 2 else None,
        "pr_auc": average_precision_score(labels, probabilities) if len(np.unique(labels)) == 2 else None,
    }
    return result


def save_metrics(metrics, path):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
