from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from online_darp_benchmark.validate import (
    ValidationFailure,
    load_document,
    load_schema,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def result_errors(document):
    validator = Draft202012Validator(
        load_schema("result"), format_checker=FormatChecker()
    )
    return list(validator.iter_errors(document))


def test_result_requires_solver_disclosure() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    del document["algorithm"]["optimization_stack"]
    assert result_errors(document)


def test_external_stack_cannot_be_empty() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["algorithm"]["optimization_stack"]["uses_external_components"] = True
    assert result_errors(document)


def test_no_external_stack_cannot_list_components() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["algorithm"]["optimization_stack"]["components"] = [
        optimization_component()
    ]
    assert result_errors(document)


def test_complete_solver_disclosure_is_valid() -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["algorithm"]["optimization_stack"] = {
        "uses_external_components": True,
        "components": [optimization_component()],
        "notes": "Example only; not a claim about a specific product.",
    }
    document["metrics"]["computation"]["external_solver_calls"] = 2
    document["metrics"]["computation"]["external_solver_wall_time_seconds"] = 0.004
    assert not result_errors(document)


def test_result_rejects_nonzero_solver_calls_without_solver(tmp_path: Path) -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    document["metrics"]["computation"]["external_solver_calls"] = 1
    path = tmp_path / "result.yaml"
    path.write_text(yaml_dump(document), encoding="utf-8")
    with pytest.raises(ValidationFailure, match="must be zero"):
        validate_manifest(path, "result")


def test_result_rejects_duplicate_component_ids(tmp_path: Path) -> None:
    document = deepcopy(load_document(ROOT / "examples/result.yaml"))
    component = optimization_component()
    document["algorithm"]["optimization_stack"] = {
        "uses_external_components": True,
        "components": [component, deepcopy(component)],
        "notes": None,
    }
    path = tmp_path / "result.yaml"
    path.write_text(yaml_dump(document), encoding="utf-8")
    with pytest.raises(ValidationFailure, match="must be unique"):
        validate_manifest(path, "result")


def optimization_component():
    return {
        "component_id": "example-solver",
        "name": "Example Solver",
        "component_type": "solver",
        "version": "1.2.3",
        "role": "online_decision",
        "license_name": "Example terms",
        "license_url": "https://example.org/terms",
        "access_class": "restricted_no_cost",
        "paid_license_used": False,
        "exact_environment_publicly_obtainable": False,
        "threads": 1,
        "parameters": {"time_limit_seconds": 1},
        "notes": None,
    }


def yaml_dump(document) -> str:
    return yaml.safe_dump(document, sort_keys=False)
