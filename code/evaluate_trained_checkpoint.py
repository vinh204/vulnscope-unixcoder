"""Choose a decision threshold on validation, then evaluate once on test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import precision_recall_curve

from data_utils import load_records
from inference import UniXcoderPredictor
from metrics import binary_metrics


def predict_split(predictor, path: Path, batch_size: int) -> pd.DataFrame:
    records = load_records(path)
    rows = []
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        predictions = predictor.predict_batch([row["func"] for row in batch])
        for row, prediction in zip(batch, predictions):
            rows.append({
                "idx": row.get("idx", len(rows)),
                "label": int(row["target"]),
                "vulnerable_probability": prediction.vulnerable_probability,
                "token_count": prediction.token_count,
                "truncated": prediction.truncated,
            })
    return pd.DataFrame(rows)


def choose_f1_threshold(labels, scores) -> tuple[float, float]:
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    if not len(thresholds):
        return 0.5, 0.0
    f1 = 2 * precision[:-1] * recall[:-1] / (precision[:-1] + recall[:-1] + 1e-12)
    best = int(f1.argmax())
    return float(thresholds[best]), float(f1[best])


def save_split(frame: pd.DataFrame, threshold: float, directory: Path, split: str) -> dict:
    frame = frame.copy()
    frame["prediction"] = (frame["vulnerable_probability"] >= threshold).astype(int)
    frame.to_csv(directory / f"{split}_predictions.csv", index=False)
    result = binary_metrics(frame["label"], frame["vulnerable_probability"], threshold)
    result["sample_count"] = len(frame)
    result["split"] = split
    result["threshold_selected_on"] = "validation" if split == "test" else None
    (directory / f"{split}_metrics.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--validation-data", default="data/devign/valid.jsonl")
    parser.add_argument("--test-data", default="data/devign/test.jsonl")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-name", default="microsoft/unixcoder-base")
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    predictor = UniXcoderPredictor(args.checkpoint, args.model_name, args.block_size, device="cpu")

    validation = predict_split(predictor, Path(args.validation_data), args.batch_size)
    threshold, validation_f1 = choose_f1_threshold(
        validation["label"], validation["vulnerable_probability"]
    )
    validation_metrics = save_split(validation, threshold, output, "validation")
    validation_metrics["threshold"] = threshold
    validation_metrics["validation_best_f1"] = validation_f1
    validation_metrics["threshold_selected_on"] = "validation"
    (output / "validation_metrics.json").write_text(
        json.dumps(validation_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Lock the threshold before reading or scoring the held-out test split.
    test = predict_split(predictor, Path(args.test_data), args.batch_size)
    test_metrics = save_split(test, threshold, output, "test")
    test_metrics["validation_best_f1"] = validation_f1
    (output / "test_metrics.json").write_text(
        json.dumps(test_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({"threshold": threshold, "validation": validation_metrics,
                      "test": test_metrics}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
