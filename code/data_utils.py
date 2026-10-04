"""Dataset I/O helpers supporting JSON arrays and JSON Lines files."""

from __future__ import annotations

import json
from pathlib import Path


def load_records(path):
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        first = handle.read(1)
        handle.seek(0)
        if first == "[":
            records = json.load(handle)
        else:
            records = [json.loads(line) for line in handle if line.strip()]
    if not isinstance(records, list):
        raise ValueError(f"Dataset phải là JSON array hoặc JSONL: {source}")
    return records
