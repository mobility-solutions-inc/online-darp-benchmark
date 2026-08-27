from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_PREFIX = "0001-parquet-instance"


def load_yaml(name: str):
    return yaml.safe_load((ROOT / "proposals" / name).read_text(encoding="utf-8"))


def test_parquet_proposal_defines_every_core_table() -> None:
    contract = load_yaml(f"{PROPOSAL_PREFIX}-format.schemas.yaml")
    assert set(contract["tables"]) == {
        "requests",
        "reveal_times",
        "vehicles",
        "nodes",
        "travel_times",
    }


def test_parquet_proposal_fields_are_unique_and_typed() -> None:
    contract = load_yaml(f"{PROPOSAL_PREFIX}-format.schemas.yaml")
    known_types = {"binary", "bool", "float64", "int32", "int64", "string"}
    for table in contract["tables"].values():
        fields = table["fields"]
        names = [field["name"] for field in fields]
        assert len(names) == len(set(names))
        assert all(field["type"] in known_types for field in fields)


def test_parquet_instance_example_composes_every_core_table() -> None:
    example = load_yaml(f"{PROPOSAL_PREFIX}.example.yaml")
    assert example["format_version"] == "1.0.0-draft.1"
    assert set(example["components"]) == {
        "requests",
        "reveal_times",
        "vehicles",
        "nodes",
        "travel_times",
    }
    assert len(example["physical_problem_sha256"]) == 64


def test_parquet_collection_resolves_instance_components() -> None:
    collection = load_yaml("0001-parquet-collection.example.yaml")
    instance = load_yaml(f"{PROPOSAL_PREFIX}.example.yaml")
    assert collection["collection_id"] == instance["collection_id"]
    assert set(instance["components"].values()) <= set(collection["artifacts"])
    for artifact in collection["artifacts"].values():
        for file_record in artifact["files"]:
            assert len(file_record["sha256"]) == 64
            assert file_record["row_count"] > 0
