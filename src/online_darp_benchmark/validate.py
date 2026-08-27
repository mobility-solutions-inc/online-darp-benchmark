"""Validate Online DARP instance, result, and event-log records."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


class ValidationFailure(ValueError):
    """Raised when a benchmark artifact violates its contract."""


def default_schema_dir() -> Path:
    """Locate schemas in a checkout, with an environment override for packaging."""

    override = os.environ.get("ONLINE_DARP_SCHEMA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "schemas"


def load_document(path: Path) -> Any:
    """Load a JSON or YAML document from *path*."""

    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            return json.load(handle)
        return yaml.safe_load(handle)


def load_schema(kind: str, schema_dir: Path | None = None) -> dict[str, Any]:
    """Load and self-check one of the benchmark JSON Schemas."""

    root = schema_dir or default_schema_dir()
    schema_path = root / f"{kind}.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValidationFailure(f"schema not found: {schema_path}") from error
    Draft202012Validator.check_schema(schema)
    return schema


def _format_error(error: Any, prefix: str = "") -> str:
    location = ".".join(str(part) for part in error.absolute_path)
    where = f"{prefix}{location}" if location else prefix.rstrip(".") or "document"
    return f"{where}: {error.message}"


def validate_manifest(
    path: Path, kind: str, schema_dir: Path | None = None
) -> dict[str, Any]:
    """Validate an instance or result manifest and return the parsed document."""

    if kind not in {"instance", "result"}:
        raise ValueError(f"unsupported manifest kind: {kind}")
    document = load_document(path)
    schema = load_schema(kind, schema_dir)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        details = "\n".join(_format_error(error) for error in errors)
        raise ValidationFailure(f"{path} failed {kind} validation:\n{details}")
    return document


def validate_event_log(
    path: Path, schema_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Validate JSONL event records plus ordering and identity invariants."""

    schema = load_schema("event", schema_dir)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    records: list[dict[str, Any]] = []
    failures: list[str] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as error:
                failures.append(f"line {line_number}: invalid JSON: {error.msg}")
                continue
            records.append(record)
            for error in validator.iter_errors(record):
                failures.append(_format_error(error, prefix=f"line {line_number}."))

    if not records:
        failures.append("event log is empty")
    else:
        run_ids = {record.get("run_id") for record in records}
        instance_ids = {record.get("instance_id") for record in records}
        if len(run_ids) != 1:
            failures.append("all records must have the same run_id")
        if len(instance_ids) != 1:
            failures.append("all records must have the same instance_id")

        sequences = [record.get("sequence") for record in records]
        if sequences != list(range(len(records))):
            failures.append("sequence must be contiguous, ordered, and start at zero")

        times = [record.get("simulation_time") for record in records]
        if all(isinstance(value, (int, float)) for value in times):
            if times != sorted(times):
                failures.append("simulation_time must be nondecreasing")

        if records[0].get("event_type") != "run_started":
            failures.append("the first event must be run_started")
        if records[-1].get("event_type") != "run_finished":
            failures.append("the last event must be run_finished")

    if failures:
        details = "\n".join(failures)
        raise ValidationFailure(f"{path} failed event validation:\n{details}")
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="odb-validate",
        description="Validate Online DARP Benchmark artifacts.",
    )
    parser.add_argument("kind", choices=("instance", "result", "events"))
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=None,
        help="directory containing *.schema.json (defaults to checkout schemas/)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.kind == "events":
            validate_event_log(args.path, args.schema_dir)
        else:
            validate_manifest(args.path, args.kind, args.schema_dir)
    except (OSError, ValidationFailure, yaml.YAMLError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"valid {args.kind}: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

