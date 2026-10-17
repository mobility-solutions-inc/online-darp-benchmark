import json
import struct
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml

from online_darp_benchmark.parquet_collection import (
    FORMAT_VERSION,
    OGC_CRS84_PROJJSON,
    CollectionValidationError,
    _geo_metadata_errors,
    _is_point_wkb,
    artifact_record,
    dump_yaml,
    main,
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
    distance_mm: int | None = None,
    onboard_requests: list[dict[str, object]] | None = None,
    reveal_rows: int | None = None,
    node_x: float | None = None,
    instance_format_version: str = FORMAT_VERSION,
    notice_paths: list[str] | None = None,
    spatial_profile: str | None = None,
    vehicle_rows: int | None = None,
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
    if distance_mm is not None:
        tables["travel_times"][1]["distance_mm"] = distance_mm
    if onboard_requests is not None:
        tables["onboard_requests"] = onboard_requests
    if reveal_rows is not None:
        tables["reveal_times"] = tables["reveal_times"][:reveal_rows]
    if vehicle_rows is not None:
        tables["vehicles"] = tables["vehicles"][:vehicle_rows]
    node_profile = "matrix_only"
    if node_x is not None:
        node_profile = "abstract_cartesian"
        for index, node in enumerate(tables["nodes"]):
            node.update({"x": node_x if index == 0 else 0.0, "y": 0.0})
    for role, rows in tables.items():
        artifact_id = f"test.{role}"
        path = tmp_path / "tables" / f"{role}.parquet"
        file_record = write_parquet(
            path,
            rows,
            schema_name=role,
            collection_id=collection_id,
            artifact_id=artifact_id,
            spatial_profile=node_profile if role == "nodes" else None,
        )
        artifacts[artifact_id] = artifact_record(
            role=role,
            file_record=file_record,
            collection_root=tmp_path,
            spatial_profile=node_profile if role == "nodes" else None,
        )
        components[role] = artifact_id

    manifest_path = "instances/test.yaml"
    instance = {
        "format_version": instance_format_version,
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
        "spatial": {"profile": spatial_profile or node_profile},
        "relocation": {"allowed": True},
    }
    dump_yaml(tmp_path / manifest_path, instance)
    dump_yaml(
        tmp_path / "collection.yaml",
        {
            "format_version": FORMAT_VERSION,
            "collection_id": collection_id,
            "license": {"notice_paths": notice_paths or []},
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
            "columns": {
                "geometry": {"encoding": "WKB", "geometry_types": ["Point"], "crs": crs}
            },
        }
        return {b"geo": json.dumps(geo).encode()}

    assert _geo_metadata_errors(metadata(OGC_CRS84_PROJJSON)) == []
    assert _geo_metadata_errors(metadata("OGC:CRS84")) == [
        "GeoParquet crs must be an explicit PROJJSON object"
    ]
    assert _geo_metadata_errors({}) == ["missing or malformed GeoParquet metadata"]


def test_validator_rejects_negative_travel_distance(tmp_path: Path) -> None:
    _write_collection(tmp_path, distance_mm=-1)
    with pytest.raises(CollectionValidationError, match="negative travel distance"):
        validate_collection(tmp_path)


def _onboard_request(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "onboard_request_index": 0,
        "onboard_request_id": "onboard-1",
        "source_request_id": None,
        "party_size": 1,
        "pickup_node_index": 0,
        "dropoff_node_index": 1,
        "earliest_pickup_time_ms": 0,
        "pickup_time_ms": 0,
        "pickup_departure_time_ms": 0,
        "assigned_vehicle_index": 0,
        "dropoff_route_position": 1,
        "max_ride_time_ms": None,
        "dropoff_service_time_ms": 0,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("assigned_vehicle_index", [-1, 1])
def test_validator_reports_invalid_onboard_vehicle_without_crashing(
    tmp_path: Path, assigned_vehicle_index: int
) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1},
        onboard_requests=[_onboard_request(assigned_vehicle_index=assigned_vehicle_index)],
    )
    with pytest.raises(CollectionValidationError, match="vehicle foreign key") as error:
        validate_collection(tmp_path)
    assert "onboard loads do not match" not in str(error.value)


@pytest.mark.parametrize(
    ("onboard_overrides", "expected_error"),
    [
        ({"dropoff_service_time_ms": -1}, "negative service time"),
        ({"max_ride_time_ms": 0}, "nonpositive maximum ride time"),
    ],
)
def test_validator_rejects_invalid_onboard_durations(
    tmp_path: Path, onboard_overrides: dict[str, int], expected_error: str
) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1},
        onboard_requests=[_onboard_request(**onboard_overrides)],
    )
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_validator_rejects_request_larger_than_every_vehicle(tmp_path: Path) -> None:
    _write_collection(tmp_path, request_overrides={"party_size": 5})
    with pytest.raises(CollectionValidationError, match="exceeds every vehicle capacity"):
        validate_collection(tmp_path)


def test_validator_reports_missing_reveal_rows_without_crashing(tmp_path: Path) -> None:
    _write_collection(tmp_path, reveal_rows=0)
    with pytest.raises(CollectionValidationError, match="reveal rows do not match"):
        validate_collection(tmp_path)


def test_validator_reports_unreadable_parquet_without_crashing(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    path = tmp_path / "tables" / "requests.parquet"
    path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])
    with pytest.raises(CollectionValidationError, match="unreadable Parquet artifact"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("request_overrides", "expected_error"),
    [
        ({"latest_dropoff_time_ms": 20_000}, "cannot reach drop-off"),
        ({"max_ride_time_ms": 20_000}, "longer than max_ride_time_ms"),
    ],
)
def test_validator_rejects_individually_infeasible_requests(
    tmp_path: Path, request_overrides: dict[str, int], expected_error: str
) -> None:
    _write_collection(tmp_path, request_overrides=request_overrides)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_validator_rejects_non_finite_coordinates(tmp_path: Path, value: float) -> None:
    _write_collection(tmp_path, node_x=value)
    with pytest.raises(CollectionValidationError, match="non-finite x values"):
        validate_collection(tmp_path)


def test_validator_accepts_finite_cartesian_coordinates(tmp_path: Path) -> None:
    _write_collection(tmp_path, node_x=1.5)
    assert validate_collection(tmp_path)["valid"] is True


def test_validator_rejects_unsupported_instance_format(tmp_path: Path) -> None:
    _write_collection(tmp_path, instance_format_version="0.0.0")
    with pytest.raises(CollectionValidationError, match="unsupported format_version: 0.0.0"):
        validate_collection(tmp_path)


def test_validator_requires_declared_license_notices(tmp_path: Path) -> None:
    _write_collection(tmp_path, notice_paths=["LICENSES/upstream-notices.md"])
    with pytest.raises(CollectionValidationError, match="missing license notice"):
        validate_collection(tmp_path)
    (tmp_path / "LICENSES").mkdir()
    (tmp_path / "LICENSES" / "upstream-notices.md").write_text("notice\n")
    assert validate_collection(tmp_path)["valid"] is True


def test_cli_writes_report_for_invalid_collection(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    _write_collection(root, request_overrides={"party_size": 0})
    report_path = tmp_path / "report.yaml"
    assert main([str(root), "--report", str(report_path)]) == 1
    report = yaml.safe_load(report_path.read_text())
    assert report["valid"] is False
    assert any("party_size below one" in error for error in report["errors"])


def _move_requests_to_uri(root: Path, uri: str) -> Path:
    collection = yaml.safe_load((root / "collection.yaml").read_text())
    file_record = collection["artifacts"]["test.requests"]["files"][0]
    external = root.parent / "external-requests.parquet"
    (root / file_record.pop("path")).rename(external)
    file_record["uri"] = uri
    dump_yaml(root / "collection.yaml", collection)
    return external


def test_validator_checks_external_uri_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    _write_collection(root)
    uri = "https://example.org/releases/v1/requests.parquet"
    external = _move_requests_to_uri(root, uri)
    fetched = []

    def fetch(requested: str) -> Path:
        fetched.append(requested)
        return external

    assert validate_collection(root, fetch_uri=fetch)["valid"] is True
    assert fetched == [uri]

    external.write_bytes(external.read_bytes() + b"tampered")
    with pytest.raises(CollectionValidationError, match="SHA-256 mismatch"):
        validate_collection(root, fetch_uri=fetch)


@pytest.mark.parametrize(
    ("uri", "expected_error"),
    [
        ("http://example.org/v1/requests.parquet", "absolute https URL"),
        ("https://example.org/releases/latest/requests.parquet", "unversioned latest"),
    ],
)
def test_validator_rejects_mutable_or_insecure_uris(
    tmp_path: Path, uri: str, expected_error: str
) -> None:
    root = tmp_path / "collection"
    _write_collection(root)
    _move_requests_to_uri(root, uri)

    def fetch(requested: str) -> Path:
        pytest.fail(f"fetched {requested}")

    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(root, fetch_uri=fetch)


def test_point_wkb_validation() -> None:
    assert _is_point_wkb(struct.pack("<BIdd", 1, 1, -73.9, 40.7))
    assert _is_point_wkb(struct.pack(">BIdd", 0, 1, -73.9, 40.7))
    assert not _is_point_wkb(struct.pack("<BIdd", 1, 2, -73.9, 40.7))
    assert not _is_point_wkb(struct.pack("<BIdd", 1, 1, float("nan"), 40.7))
    assert not _is_point_wkb(b"\x01\x01\x00")


def test_validator_rejects_mismatched_spatial_profile(tmp_path: Path) -> None:
    _write_collection(tmp_path, spatial_profile="geographic")
    with pytest.raises(CollectionValidationError, match="does not match nodes artifact"):
        validate_collection(tmp_path)


def test_validator_rejects_demand_without_vehicles(tmp_path: Path) -> None:
    _write_collection(tmp_path, vehicle_rows=0)
    with pytest.raises(CollectionValidationError, match="no vehicles to serve them"):
        validate_collection(tmp_path)
