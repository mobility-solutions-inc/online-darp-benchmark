import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml

from online_darp_benchmark.parquet_collection import (
    FORMAT_VERSION,
    OGC_CRS84_PROJJSON,
    CollectionValidationError,
    _geo_metadata_errors,
    artifact_record,
    dump_yaml,
    physical_problem_sha256,
    validate_collection,
    write_parquet,
)


def _write_collection(
    tmp_path: Path,
    *,
    vehicle_overrides: dict[str, object] | None = None,
    request_overrides: dict[str, object] | None = None,
    travel_time_rows: int | None = None,
) -> None:
    collection_id = "test-collection"
    artifacts = {}
    components = {}
    tables = {
        "requests": [
            {
                "request_index": 0,
                "request_id": "request-1",
                "source_request_id": "1",
                "party_size": 1,
                "pickup_node_index": 0,
                "dropoff_node_index": 1,
                "earliest_pickup_time_ms": 0,
                "latest_pickup_time_ms": 60_000,
                "earliest_dropoff_time_ms": None,
                "latest_dropoff_time_ms": 120_000,
                "max_ride_time_ms": 120_000,
                "pickup_service_time_ms": 0,
                "dropoff_service_time_ms": 0,
            }
        ],
        "reveal_times": [{"request_index": 0, "base_reveal_time_ms": 0}],
        "vehicles": [
            {
                "vehicle_index": 0,
                "vehicle_id": "vehicle-1",
                "source_vehicle_id": "1",
                "start_node_index": 0,
                "end_node_index": 0,
                "shift_start_time_ms": 0,
                "shift_end_time_ms": 300_000,
                "max_route_duration_ms": None,
                "seat_capacity": 4,
                "initial_load": 0,
            }
        ],
        "nodes": [
            {
                "node_index": 0,
                "node_id": "node-0",
                "source_node_id": "0",
                "relocation_allowed": True,
            },
            {
                "node_index": 1,
                "node_id": "node-1",
                "source_node_id": "1",
                "relocation_allowed": True,
            },
        ],
        "travel_times": [
            {
                "from_node_index": origin,
                "to_node_index": destination,
                "travel_time_ms": 0 if origin == destination else 30_000,
                "distance_mm": None,
            }
            for origin in range(2)
            for destination in range(2)
        ],
    }
    tables["vehicles"][0].update(vehicle_overrides or {})
    tables["requests"][0].update(request_overrides or {})
    if travel_time_rows is not None:
        tables["travel_times"] = tables["travel_times"][:travel_time_rows]
    for role, rows in tables.items():
        artifact_id = f"test.{role}"
        path = tmp_path / "tables" / f"{role}.parquet"
        file_record = write_parquet(
            path,
            rows,
            schema_name=role,
            collection_id=collection_id,
            artifact_id=artifact_id,
            spatial_profile="matrix_only" if role == "nodes" else None,
        )
        artifacts[artifact_id] = artifact_record(
            role=role,
            file_record=file_record,
            collection_root=tmp_path,
            spatial_profile="matrix_only" if role == "nodes" else None,
        )
        components[role] = artifact_id

    manifest_path = "instances/test.yaml"
    instance = {
        "format_version": FORMAT_VERSION,
        "instance_id": "test",
        "physical_problem_id": "test",
        "physical_problem_sha256": physical_problem_sha256(
            components,
            artifacts,
            service_horizon_ms=300_000,
            relocation_allowed=True,
        ),
        "problem_family": "darp",
        "tier": "test",
        "collection_id": collection_id,
        "components": components,
        "time": {"service_horizon_ms": 300_000},
        "relocation": {"allowed": True},
    }
    dump_yaml(tmp_path / manifest_path, instance)
    dump_yaml(
        tmp_path / "collection.yaml",
        {
            "format_version": FORMAT_VERSION,
            "collection_id": collection_id,
            "artifacts": artifacts,
            "instances": [manifest_path],
        },
    )



def test_reference_writer_and_validator_round_trip(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    report = validate_collection(tmp_path)
    assert report["valid"] is True
    schema_metadata = pq.read_schema(tmp_path / "tables" / "requests.parquet").metadata
    assert schema_metadata[b"online_darp.schema_name"] == b"requests"


@pytest.mark.parametrize(
    ("vehicle_overrides", "expected_error"),
    [
        (
            {"shift_start_time_ms": 300_000, "shift_end_time_ms": 0},
            "reversed vehicle shift",
        ),
        ({"max_route_duration_ms": 0}, "nonpositive maximum route duration"),
        ({"max_route_duration_ms": -1}, "nonpositive maximum route duration"),
    ],
)
def test_validator_rejects_invalid_vehicle_availability(
    tmp_path: Path, vehicle_overrides: dict[str, int], expected_error: str
) -> None:
    _write_collection(tmp_path, vehicle_overrides=vehicle_overrides)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("request_overrides", "expected_error"),
    [
        ({"earliest_pickup_time_ms": -1}, "negative earliest pickup time"),
        ({"pickup_service_time_ms": -1}, "negative service time"),
        ({"dropoff_service_time_ms": -1}, "negative service time"),
        ({"max_ride_time_ms": 0}, "nonpositive maximum ride time"),
    ],
)
def test_validator_rejects_invalid_request_timing(
    tmp_path: Path, request_overrides: dict[str, int], expected_error: str
) -> None:
    _write_collection(tmp_path, request_overrides=request_overrides)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_validator_reports_short_matrix_without_crashing(tmp_path: Path) -> None:
    _write_collection(tmp_path, travel_time_rows=3)
    with pytest.raises(CollectionValidationError, match="not K squared"):
        validate_collection(tmp_path)


@pytest.mark.parametrize("escape", ["outside", "absolute"])
def test_validator_rejects_paths_outside_collection_root(
    tmp_path: Path, escape: str
) -> None:
    root = tmp_path / "collection"
    _write_collection(root)
    collection = yaml.safe_load((root / "collection.yaml").read_text())
    file_record = collection["artifacts"]["test.requests"]["files"][0]
    outside = tmp_path / "requests.parquet"
    (root / file_record["path"]).rename(outside)
    file_record["path"] = (
        "../requests.parquet" if escape == "outside" else outside.as_posix()
    )
    dump_yaml(root / "collection.yaml", collection)

    with pytest.raises(CollectionValidationError, match="escapes collection root"):
        validate_collection(root)


def test_geographic_metadata_requires_projjson_crs() -> None:
    def metadata(crs: object) -> dict[bytes, bytes]:
        geo = {
            "version": "1.1.0",
            "primary_column": "geometry",
            "columns": {"geometry": {"encoding": "WKB", "crs": crs}},
        }
        return {b"geo": json.dumps(geo).encode()}

    assert _geo_metadata_errors(metadata(OGC_CRS84_PROJJSON)) == []
    assert _geo_metadata_errors(metadata("OGC:CRS84")) == [
        "GeoParquet crs must be an explicit PROJJSON object"
    ]
    assert _geo_metadata_errors({}) == ["missing or malformed GeoParquet metadata"]
