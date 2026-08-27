from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from online_darp_benchmark.validate import (
    ValidationFailure,
    load_document,
    load_schema,
    validate_event_log,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def test_example_instance_is_valid() -> None:
    document = validate_manifest(ROOT / "examples/instance.yaml", "instance")
    assert document["requests"]["request_count"] == 2


def test_example_result_is_valid() -> None:
    document = validate_manifest(ROOT / "examples/result.yaml", "result")
    assert document["metrics"]["service"]["request_service_rate"] == 0.5


def test_example_event_log_is_valid() -> None:
    records = validate_event_log(ROOT / "examples/event-log.jsonl")
    assert records[0]["event_type"] == "run_started"
    assert records[-1]["event_type"] == "run_finished"


def test_result_contract_rejects_an_aggregate_score() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["metrics"]["overall_score"] = 0.99
    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_event_log_rejects_nonmonotonic_time(tmp_path: Path) -> None:
    lines = (ROOT / "examples/event-log.jsonl").read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"simulation_time":0', '"simulation_time":999')
    broken = tmp_path / "events.jsonl"
    broken.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValidationFailure, match="nondecreasing"):
        validate_event_log(broken)

