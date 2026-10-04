"""Create the official CodeXGLUE Devign splits from function.json."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def read_indices(path):
    return [int(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/devign")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    functions = json.loads((data_dir / "function.json").read_text(encoding="utf-8"))

    summary = {}
    for split in ("train", "valid", "test"):
        indices = read_indices(data_dir / f"{split}.txt")
        destination = data_dir / f"{split}.jsonl"
        labels = Counter()
        with destination.open("w", encoding="utf-8", newline="\n") as output:
            for index in indices:
                record = dict(functions[index])
                record["idx"] = index
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                labels[int(record["target"])] += 1
        summary[split] = {"total": len(indices), "safe": labels[0], "vulnerable": labels[1]}

    (data_dir / "dataset_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
