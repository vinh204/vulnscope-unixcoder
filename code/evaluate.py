"""Evaluate a trained checkpoint and export dashboard artifacts."""

import argparse
import json
from pathlib import Path

import pandas as pd

from inference import UniXcoderPredictor
from metrics import binary_metrics, save_metrics
from data_utils import load_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="JSON array with input/output fields")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--model-name", default="microsoft/unixcoder-base")
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--code-key", default="func")
    parser.add_argument("--label-key", default="target")
    parser.add_argument("--head", type=int, default=None, help="Evaluate only the first N records")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    samples = load_records(args.data)
    if args.head is not None:
        samples = samples[:args.head]
    predictor = UniXcoderPredictor(args.checkpoint, args.model_name, args.block_size)
    rows = []
    for start in range(0, len(samples), args.batch_size):
        batch = samples[start:start + args.batch_size]
        results = predictor.predict_batch([sample[args.code_key] for sample in batch])
        for offset, (sample, result) in enumerate(zip(batch, results)):
            position = start + offset
            rows.append({"idx": sample.get("idx", position), "CWE": sample.get("CWE", "Unknown"),
                         "label": int(sample[args.label_key]),
                         "prediction": int(result.vulnerable_probability >= args.threshold),
                         "vulnerable_probability": result.vulnerable_probability,
                         "token_count": result.token_count, "truncated": result.truncated})
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "predictions.csv", index=False)
    metrics = binary_metrics(frame["label"], frame["vulnerable_probability"], args.threshold)
    save_metrics(metrics, output / "metrics.json")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
