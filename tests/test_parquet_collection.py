from pathlib import Path

import pyarrow.parquet as pq

from online_darp_benchmark.parquet_collection import (
    FORMAT_VERSION,
    artifact_record,
    dump_yaml,
    physical_problem_sha256,
    validate_collection,
    write_parquet,
)


def test_reference_writer_and_validator_round_trip(tmp_path: Path) -> None:
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

    report = validate_collection(tmp_path)
    assert report["valid"] is True
    schema_metadata = pq.read_schema(tmp_path / "tables" / "requests.parquet").metadata
    assert schema_metadata[b"online_darp.schema_name"] == b"requests"
