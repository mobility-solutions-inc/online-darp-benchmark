from copy import deepcopy
from pathlib import Path

import pytest
import yaml
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
    assert document["algorithm"]["code_available_publicly"] is True
    assert document["algorithm"]["public_code_url"].startswith("https://")


def test_synthetic_hidden_submission_is_valid() -> None:
    document = validate_manifest(
        ROOT / "examples/hidden-instance-submission.yaml", "hidden-instance"
    )
    assert document["visibility"] == "hidden"


def test_synthetic_hidden_access_ledger_is_valid() -> None:
    document = validate_manifest(
        ROOT / "examples/hidden-access-ledger.yaml", "hidden-access-ledger"
    )
    assert document["entries"][0]["role"] == "contributor"


def test_public_hidden_suite_registry_is_valid() -> None:
    document = validate_manifest(
        ROOT / "manifests/hidden-suites.yaml", "hidden-suite-registry"
    )
    assert document["entries"] == []


def test_hidden_contributor_reference_result_is_valid() -> None:
    document = validate_manifest(
        ROOT / "examples/hidden-reference-result.yaml", "result"
    )
    assert document["standing"]["classification"] == "contributor_reference"
    assert document["standing"]["official"] is False


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


def test_public_code_requires_a_link() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["algorithm"]["public_code_url"] = None
    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_nonpublic_code_rejects_a_public_link() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["algorithm"]["code_available_publicly"] = False
    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_official_hidden_result_requires_no_algorithm_team_access() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    standing = document["standing"]
    standing["instance_visibility"] = "hidden"
    standing["classification"] = "official"
    standing["official"] = True
    standing["access"]["controlled_evaluation"] = True
    standing["access"]["evaluation_operator"] = "Independent Evaluator"
    standing["access"]["access_attestation_uri"] = (
        "https://example.invalid/access-attestation"
    )
    standing["access"]["algorithm_team_had_pre_evaluation_access"] = True
    document["algorithm"]["team"][0]["github"] = "synthetic-author"

    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_public_result_requires_instance_checksum() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["instance_sha256"] = None
    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_official_hidden_result_accepts_independent_controlled_evaluation() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    standing = document["standing"]
    standing["instance_visibility"] = "hidden"
    standing["classification"] = "official"
    standing["official"] = True
    standing["access"]["controlled_evaluation"] = True
    standing["access"]["evaluation_operator"] = "Independent Evaluator"
    standing["access"]["access_attestation_uri"] = (
        "https://example.invalid/access-attestation"
    )
    document["algorithm"]["team"][0]["github"] = "synthetic-author"

    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert not list(validator.iter_errors(document))


def test_contributor_reference_requires_a_hidden_access_conflict() -> None:
    document = deepcopy(load_document(ROOT / "examples/hidden-reference-result.yaml"))
    access = document["standing"]["access"]
    access["instance_contributor_involved"] = False
    access["algorithm_team_had_pre_evaluation_access"] = False

    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_contributor_reference_cannot_be_official() -> None:
    document = deepcopy(load_document(ROOT / "examples/hidden-reference-result.yaml"))
    document["standing"]["official"] = True
    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    assert list(validator.iter_errors(document))


def test_connor_standing_conflict_is_machine_readable() -> None:
    conflicts = load_document(ROOT / "manifests/hidden-conflicts.yaml")
    connor = next(
        entry for entry in conflicts["entries"] if entry["github"] == "ctriley"
    )
    assert connor["restriction"]["official_hidden_result_eligible"] is False
    assert set(connor["restriction"]["allowed_hidden_classifications"]) == {
        "contributor_reference",
        "unofficial",
    }


def test_connor_algorithm_is_rejected_as_official_on_hidden_data(
    tmp_path: Path,
) -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    standing = document["standing"]
    standing["instance_visibility"] = "hidden"
    standing["classification"] = "official"
    standing["official"] = True
    standing["access"]["controlled_evaluation"] = True
    standing["access"]["evaluation_operator"] = "Independent Evaluator"
    standing["access"]["access_attestation_uri"] = (
        "https://example.invalid/access-attestation"
    )
    document["algorithm"]["team"] = [
        {"name": "Connor Riley", "github": "ctriley", "roles": ["author"]}
    ]
    submitted = tmp_path / "connor-official-hidden.yaml"
    submitted.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationFailure, match="Connor Riley"):
        validate_manifest(submitted, "result")


def test_event_log_rejects_nonmonotonic_time(tmp_path: Path) -> None:
    lines = (ROOT / "examples/event-log.jsonl").read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"simulation_time":0', '"simulation_time":999')
    broken = tmp_path / "events.jsonl"
    broken.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValidationFailure, match="nondecreasing"):
        validate_event_log(broken)
