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
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Every dataset record must be a JSON object: {source}")
    return records


def validate_code_records(records, path="dataset"):
    """Fail early on malformed code-classification samples."""
    if not records:
        raise ValueError(f"Dataset is empty: {path}")
    for index, record in enumerate(records):
        missing = {"func", "target"} - record.keys()
        if missing:
            raise ValueError(f"Record {index} in {path} is missing: {', '.join(sorted(missing))}")
        if not isinstance(record["func"], str):
            raise ValueError(f"Record {index} in {path} has a non-string func field")
        raw_label = record["target"]
        if isinstance(raw_label, bool) or not isinstance(raw_label, (int, str)):
            raise ValueError(f"Record {index} in {path} has a non-integer target")
        try:
            label = int(raw_label)
        except ValueError as exc:
            raise ValueError(f"Record {index} in {path} has a non-integer target") from exc
        if label not in (0, 1):
            raise ValueError(f"Record {index} in {path} has target={label}; expected 0 or 1")
    return records
