import json
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    sha256_file,
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
    node_count: int = 2,
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
                "node_index": index,
                "node_id": f"node-{index}",
                "source_node_id": str(index),
                "relocation_allowed": True,
            }
            for index in range(node_count)
        ],
        "travel_times": [
            {
                "from_node_index": origin,
                "to_node_index": destination,
                "travel_time_ms": 0 if origin == destination else 30_000,
                "distance_mm": None,
            }
            for origin in range(node_count)
            for destination in range(node_count)
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
        "relocation": {"allowed": True, "destinations": "nodes.relocation_allowed"},
    }
    dump_yaml(tmp_path / manifest_path, instance)
    dump_yaml(
        tmp_path / "collection.yaml",
        {
            "format_version": FORMAT_VERSION,
            "collection_id": collection_id,
            "collection_version": "0.0.0-test",
            "source": {
                "source_id": "test",
                "source_release": "v0",
                "canonical_url": "https://example.org/test",
                "citations": ["Test fixture"],
            },
            "license": {"spdx_or_name": "MIT", "notice_paths": notice_paths or []},
            "artifacts": artifacts,
            "transformations": [
                {
                    "transformation_id": "test",
                    "code_url": "https://example.org/code",
                    "code_version": "test",
                    "parameters": {},
                    "random_seed": None,
                    "deterministic": True,
                }
            ],
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
    assert _geo_metadata_errors(metadata({})) == [
        "GeoParquet crs must be an explicit PROJJSON object"
    ]
    assert _geo_metadata_errors(metadata({"type": "GeographicCRS"})) == [
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


@pytest.mark.parametrize(
    "vehicle_overrides",
    [
        {"shift_start_time_ms": 0, "shift_end_time_ms": 20_000},
        {"shift_start_time_ms": 100_000, "shift_end_time_ms": 300_000},
    ],
)
def test_validator_rejects_requests_outside_every_vehicle_shift(
    tmp_path: Path, vehicle_overrides: dict[str, int]
) -> None:
    _write_collection(tmp_path, vehicle_overrides=vehicle_overrides)
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_validator_reports_schema_mismatch_without_crashing(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    file_record = collection["artifacts"]["test.requests"]["files"][0]
    path = tmp_path / file_record["path"]
    table = pq.read_table(path)
    pq.write_table(table.drop_columns(["party_size"]), path)
    file_record["sha256"] = sha256_file(path)
    file_record["byte_size"] = path.stat().st_size
    dump_yaml(tmp_path / "collection.yaml", collection)

    with pytest.raises(CollectionValidationError, match="schema mismatch") as error:
        validate_collection(tmp_path)
    assert "unresolved component" in str(error.value)


def test_validator_rejects_reused_physical_problem_id(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    instance = yaml.safe_load((tmp_path / "instances/test.yaml").read_text())
    instance["instance_id"] = "test-short-horizon"
    instance["time"]["service_horizon_ms"] = 200_000
    instance["physical_problem_sha256"] = physical_problem_sha256(
        instance["components"],
        collection["artifacts"],
        service_horizon_ms=200_000,
        relocation_allowed=True,
    )
    dump_yaml(tmp_path / "instances/test-short-horizon.yaml", instance)
    collection["instances"].append("instances/test-short-horizon.yaml")
    dump_yaml(tmp_path / "collection.yaml", collection)

    with pytest.raises(CollectionValidationError, match="reused for a different physical"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("remove", "expected_error"),
    [
        (("collection_version",), "missing collection_version"),
        (("source", "citations"), "missing source.citations"),
        (("license", "spdx_or_name"), "missing license.spdx_or_name"),
        (("transformations",), "missing transformations"),
    ],
)
def test_validator_requires_collection_manifest_fields(
    tmp_path: Path, remove: tuple[str, ...], expected_error: str
) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    parent = collection
    for key in remove[:-1]:
        parent = parent[key]
    del parent[remove[-1]]
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_validator_requires_registered_sort_keys(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    collection["artifacts"]["test.requests"]["sort_keys"] = ["request_id"]
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match="sort_keys must be"):
        validate_collection(tmp_path)


def test_validator_applies_max_route_duration_to_serviceability(tmp_path: Path) -> None:
    _write_collection(tmp_path, vehicle_overrides={"max_route_duration_ms": 20_000})
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    "onboard_overrides",
    [
        {"earliest_pickup_time_ms": 10, "pickup_time_ms": 0, "pickup_departure_time_ms": 10},
        {"pickup_time_ms": 10, "pickup_departure_time_ms": 5},
    ],
)
def test_validator_rejects_impossible_onboard_chronology(
    tmp_path: Path, onboard_overrides: dict[str, int]
) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1},
        onboard_requests=[_onboard_request(**onboard_overrides)],
    )
    with pytest.raises(CollectionValidationError, match="impossible onboard pickup chronology"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("uri", "valid"),
    [
        ("https://raw.githubusercontent.com/org/repo/main/table.parquet", False),
        ("https://github.com/org/repo/raw/v1.0/table.parquet", False),
        ("https://gitlab.com/org/repo/-/raw/main/table.parquet", False),
        ("https://raw.githubusercontent.com:443/org/repo/main/table.parquet", False),
        ("https://user@github.com/org/repo/blob/main/table.parquet", False),
        (f"https://raw.githubusercontent.com/org/repo/{'a' * 40}/table.parquet", True),
        ("https://github.com/org/repo/releases/download/v1.0/table.parquet", True),
    ],
)
def test_validator_rejects_branch_artifact_uris(tmp_path: Path, uri: str, valid: bool) -> None:
    root = tmp_path / "collection"
    _write_collection(root)
    external = _move_requests_to_uri(root, uri)
    if valid:
        assert validate_collection(root, fetch_uri=lambda requested: external)["valid"]
    else:
        with pytest.raises(CollectionValidationError, match="full commit hash"):
            validate_collection(root, fetch_uri=lambda requested: external)


@pytest.mark.parametrize(
    ("vehicle_overrides", "request_overrides"),
    [
        ({"start_node_index": 1}, {"latest_pickup_time_ms": 10_000}),
        ({"shift_end_time_ms": 50_000}, {}),
        ({"max_route_duration_ms": 50_000}, {}),
    ],
)
def test_serviceability_includes_positioning_travel(
    tmp_path: Path, vehicle_overrides: dict[str, int], request_overrides: dict[str, int]
) -> None:
    _write_collection(
        tmp_path, vehicle_overrides=vehicle_overrides, request_overrides=request_overrides
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_validator_requires_core_instance_components(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    instance = yaml.safe_load((tmp_path / "instances/test.yaml").read_text())
    del instance["components"]["nodes"]
    dump_yaml(tmp_path / "instances/test.yaml", instance)
    with pytest.raises(CollectionValidationError, match="missing components nodes"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (lambda instance: instance.pop("time"), "service_horizon_ms must be"),
        (lambda instance: instance["relocation"].pop("allowed"), "relocation.allowed"),
        (lambda instance: instance.update(collection_id="other"), "collection_id must be"),
        (lambda instance: instance.pop("physical_problem_id"), "missing physical_problem_id"),
        (
            lambda instance: instance["components"].update(requests="test.vehicles"),
            "wrong-role artifacts: requests",
        ),
        (
            lambda instance: instance["components"].update(extra="test.nodes"),
            "unknown components extra",
        ),
    ],
)
def test_validator_reports_malformed_instance_manifests(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], object], expected_error: str
) -> None:
    _write_collection(tmp_path)
    instance = yaml.safe_load((tmp_path / "instances/test.yaml").read_text())
    mutate(instance)
    dump_yaml(tmp_path / "instances/test.yaml", instance)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("onboard_overrides", "vehicle_overrides", "expected_error"),
    [
        (
            {
                "earliest_pickup_time_ms": -10_000,
                "pickup_time_ms": -10_000,
                "pickup_departure_time_ms": -10_000,
                "max_ride_time_ms": 5_000,
            },
            {},
            "cannot reach drop-off within max_ride_time_ms",
        ),
        ({}, {"shift_end_time_ms": 20_000}, "cannot be dropped off within"),
    ],
)
def test_validator_rejects_impossible_onboard_deadlines(
    tmp_path: Path,
    onboard_overrides: dict[str, int],
    vehicle_overrides: dict[str, int],
    expected_error: str,
) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1, **vehicle_overrides},
        onboard_requests=[_onboard_request(**onboard_overrides)],
    )
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_validator_accepts_reachable_onboard_deadline(tmp_path: Path) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1},
        onboard_requests=[_onboard_request(max_ride_time_ms=60_000)],
    )
    assert validate_collection(tmp_path)["valid"] is True


@pytest.mark.parametrize("section", ["time", "spatial", "relocation"])
def test_validator_reports_scalar_instance_sections(tmp_path: Path, section: str) -> None:
    _write_collection(tmp_path)
    instance = yaml.safe_load((tmp_path / "instances/test.yaml").read_text())
    instance[section] = "invalid"
    dump_yaml(tmp_path / "instances/test.yaml", instance)
    with pytest.raises(CollectionValidationError, match=f"{section} must be a mapping"):
        validate_collection(tmp_path)


def _add_extension_column(root: Path, name: str, declaration: dict[str, object] | None) -> None:
    import pyarrow as pa

    collection = yaml.safe_load((root / "collection.yaml").read_text())
    artifact = collection["artifacts"]["test.requests"]
    file_record = artifact["files"][0]
    path = root / file_record["path"]
    table = pq.read_table(path)
    table = table.append_column(pa.field(name, pa.string()), pa.array(["note"]))
    pq.write_table(table, path)
    file_record["sha256"] = sha256_file(path)
    file_record["byte_size"] = path.stat().st_size
    if declaration is not None:
        artifact["extension_columns"] = [{"name": name, **declaration}]
    dump_yaml(root / "collection.yaml", collection)
    instance = yaml.safe_load((root / "instances/test.yaml").read_text())
    instance["physical_problem_sha256"] = physical_problem_sha256(
        instance["components"],
        collection["artifacts"],
        service_horizon_ms=instance["time"]["service_horizon_ms"],
        relocation_allowed=instance["relocation"]["allowed"],
    )
    dump_yaml(root / "instances/test.yaml", instance)


EXTENSION_DECLARATION = {
    "arrow_type": "string",
    "nullable": True,
    "unit": None,
    "semantics": "Free-text dispatcher note.",
    "owner": "ontra",
}


def test_validator_accepts_declared_extension_columns(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    _add_extension_column(tmp_path, "x_ontra__dispatch_note", EXTENSION_DECLARATION)
    assert validate_collection(tmp_path)["valid"] is True


@pytest.mark.parametrize(
    ("name", "declaration", "expected_error"),
    [
        ("x_ontra__dispatch_note", None, "undeclared column x_ontra__dispatch_note"),
        ("dispatch_note", EXTENSION_DECLARATION, "must match x_<organization>__<column>"),
        (
            "x_ontra__dispatch_note",
            {**EXTENSION_DECLARATION, "arrow_type": "int64"},
            "type string is not int64",
        ),
        (
            "x_ontra__dispatch_note",
            {key: value for key, value in EXTENSION_DECLARATION.items() if key != "owner"},
            "missing owner",
        ),
    ],
)
def test_validator_rejects_invalid_extension_columns(
    tmp_path: Path, name: str, declaration: dict[str, object] | None, expected_error: str
) -> None:
    _write_collection(tmp_path)
    _add_extension_column(tmp_path, name, declaration)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_validator_applies_route_duration_to_onboard_riders(tmp_path: Path) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1, "max_route_duration_ms": 20_000},
        onboard_requests=[_onboard_request()],
    )
    with pytest.raises(CollectionValidationError, match="shift and route duration"):
        validate_collection(tmp_path)


def test_validator_rejects_duplicate_instance_ids(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    (tmp_path / "instances/copy.yaml").write_text((tmp_path / "instances/test.yaml").read_text())
    collection["instances"].append("instances/copy.yaml")
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match="duplicate instance_id"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("vehicle_overrides", "request_overrides"),
    [
        ({"start_node_index": 1}, {"latest_dropoff_time_ms": 50_000}),
        ({"initial_load": 4}, {"latest_pickup_time_ms": 0}),
    ],
)
def test_serviceability_includes_dropoff_windows_and_onboard_seats(
    tmp_path: Path, vehicle_overrides: dict[str, int], request_overrides: dict[str, int]
) -> None:
    onboard = (
        [_onboard_request(party_size=4)] if vehicle_overrides.get("initial_load") else None
    )
    _write_collection(
        tmp_path,
        vehicle_overrides=vehicle_overrides,
        request_overrides=request_overrides,
        onboard_requests=onboard,
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_serviceability_allows_free_seats_with_onboard_riders(tmp_path: Path) -> None:
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 3},
        request_overrides={"latest_pickup_time_ms": 0},
        onboard_requests=[_onboard_request(party_size=3)],
    )
    assert validate_collection(tmp_path)["valid"] is True


def test_validator_requires_registered_relocation_policy(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    instance = yaml.safe_load((tmp_path / "instances/test.yaml").read_text())
    instance["relocation"]["destinations"] = "anywhere"
    dump_yaml(tmp_path / "instances/test.yaml", instance)
    with pytest.raises(CollectionValidationError, match="relocation.destinations must be"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(("onboard_parties", "valid"), [((4,), True), ((2, 2), False)])
def test_serviceability_releases_enough_onboard_seats(
    tmp_path: Path, onboard_parties: tuple[int, ...], valid: bool
) -> None:
    onboard = [
        _onboard_request(
            onboard_request_index=index,
            onboard_request_id=f"onboard-{index}",
            party_size=party,
            dropoff_service_time_ms=10_000,
        )
        for index, party in enumerate(onboard_parties)
    ]
    # One stop frees the seats in 70 s; two stops need at least 80 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 4},
        request_overrides={"party_size": 4, "latest_pickup_time_ms": 75_000},
        onboard_requests=onboard,
    )
    if valid:
        assert validate_collection(tmp_path)["valid"] is True
    else:
        with pytest.raises(CollectionValidationError, match="within its shift and limits"):
            validate_collection(tmp_path)


@pytest.mark.parametrize(("max_route_duration_ms", "valid"), [(180_000, True), (150_000, False)])
def test_serviceability_counts_unavoidable_dropoff_wait(
    tmp_path: Path, max_route_duration_ms: int, valid: bool
) -> None:
    # Latest pickup 60 s plus 30 s travel still waits 110 s for the 200 s drop-off.
    _write_collection(
        tmp_path,
        vehicle_overrides={"max_route_duration_ms": max_route_duration_ms},
        request_overrides={
            "earliest_dropoff_time_ms": 200_000,
            "latest_dropoff_time_ms": 250_000,
            "max_ride_time_ms": None,
        },
    )
    if valid:
        assert validate_collection(tmp_path)["valid"] is True
    else:
        with pytest.raises(CollectionValidationError, match="within its shift and limits"):
            validate_collection(tmp_path)


@pytest.mark.parametrize(("max_ride_time_ms", "valid"), [(120_000, True), (50_000, False)])
def test_max_ride_includes_unavoidable_dropoff_wait(
    tmp_path: Path, max_ride_time_ms: int, valid: bool
) -> None:
    # Pickup must happen by 0 s, but drop-off cannot start before 100 s.
    _write_collection(
        tmp_path,
        request_overrides={
            "latest_pickup_time_ms": 0,
            "earliest_dropoff_time_ms": 100_000,
            "max_ride_time_ms": max_ride_time_ms,
        },
    )
    if valid:
        assert validate_collection(tmp_path)["valid"] is True
    else:
        with pytest.raises(CollectionValidationError, match="shortest ride longer"):
            validate_collection(tmp_path)


def test_validator_checks_unreferenced_artifacts(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    requests = pq.read_table(tmp_path / "tables" / "requests.parquet").to_pylist()
    requests[0]["party_size"] = 0
    file_record = write_parquet(
        tmp_path / "tables" / "orphan-requests.parquet",
        requests,
        schema_name="requests",
        collection_id="test-collection",
        artifact_id="test.orphan-requests",
    )
    collection["artifacts"]["test.orphan-requests"] = artifact_record(
        role="requests", file_record=file_record, collection_root=tmp_path
    )
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match="test.orphan-requests: party_size"):
        validate_collection(tmp_path)


def test_positioning_starts_no_earlier_than_simulation_time_zero(tmp_path: Path) -> None:
    # A shift that "started" 30 s before the simulation cannot pre-position the vehicle.
    _write_collection(
        tmp_path,
        vehicle_overrides={"start_node_index": 1, "shift_start_time_ms": -30_000},
        request_overrides={"latest_pickup_time_ms": 0},
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_onboard_rider_cannot_leave_before_pickup_departure(tmp_path: Path) -> None:
    # Driving straight to drop-off and back takes 60 s, but the rider departs at 100 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1, "shift_end_time_ms": 70_000},
        onboard_requests=[
            _onboard_request(
                earliest_pickup_time_ms=100_000,
                pickup_time_ms=100_000,
                pickup_departure_time_ms=100_000,
            )
        ],
    )
    with pytest.raises(CollectionValidationError, match="cannot be dropped off within"):
        validate_collection(tmp_path)


def test_onboard_route_duration_counts_elapsed_warm_start_time(tmp_path: Path) -> None:
    # Departed at -100 s with 60 s of work left: at least 160 s against a 120 s limit.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1, "max_route_duration_ms": 120_000},
        request_overrides={"max_ride_time_ms": None},
        onboard_requests=[
            _onboard_request(
                earliest_pickup_time_ms=-100_000,
                pickup_time_ms=-100_000,
                pickup_departure_time_ms=-100_000,
            )
        ],
    )
    with pytest.raises(CollectionValidationError, match="shift and route duration"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("rows", "expected_error"),
    [
        (
            [(0, 0, 0), (0, 0, 0), (1, 1, 0)],
            "travel keys must be unique and sorted",
        ),
        ([(0, 1, 5), (0, 0, 0), (1, 1, 0)], "travel keys must be unique and sorted"),
        ([(0, 0, 7), (0, 1, 5), (1, 1, 0)], "nonzero travel matrix diagonal"),
    ],
)
def test_validator_checks_unreferenced_travel_table_keys(
    tmp_path: Path, rows: list[tuple[int, int, int]], expected_error: str
) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    file_record = write_parquet(
        tmp_path / "tables" / "orphan-travel.parquet",
        [
            {
                "from_node_index": origin,
                "to_node_index": destination,
                "travel_time_ms": travel,
                "distance_mm": None,
            }
            for origin, destination, travel in rows
        ],
        schema_name="travel_times",
        collection_id="test-collection",
        artifact_id="test.orphan-travel",
    )
    collection["artifacts"]["test.orphan-travel"] = artifact_record(
        role="travel_times", file_record=file_record, collection_root=tmp_path
    )
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_serviceability_is_checked_per_onboard_state(tmp_path: Path) -> None:
    # Same requests, fleet, and matrix; only the second onboard state blocks the pickup.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 4},
        request_overrides={"party_size": 4, "latest_pickup_time_ms": 75_000},
        onboard_requests=[_onboard_request(party_size=4, dropoff_service_time_ms=10_000)],
    )
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    blocked = [
        _onboard_request(
            onboard_request_index=index,
            onboard_request_id=f"onboard-{index}",
            party_size=2,
            dropoff_service_time_ms=10_000,
        )
        for index in range(2)
    ]
    file_record = write_parquet(
        tmp_path / "tables" / "onboard-blocked.parquet",
        blocked,
        schema_name="onboard_requests",
        collection_id="test-collection",
        artifact_id="test.onboard-blocked",
    )
    collection["artifacts"]["test.onboard-blocked"] = artifact_record(
        role="onboard_requests", file_record=file_record, collection_root=tmp_path
    )
    instance = yaml.safe_load((tmp_path / "instances/test.yaml").read_text())
    instance["instance_id"] = "test-blocked"
    instance["physical_problem_id"] = "test-blocked"
    instance["components"]["onboard_requests"] = "test.onboard-blocked"
    instance["physical_problem_sha256"] = physical_problem_sha256(
        instance["components"],
        collection["artifacts"],
        service_horizon_ms=instance["time"]["service_horizon_ms"],
        relocation_allowed=True,
    )
    dump_yaml(tmp_path / "instances/test-blocked.yaml", instance)
    collection["instances"].append("instances/test-blocked.yaml")
    dump_yaml(tmp_path / "collection.yaml", collection)

    with pytest.raises(CollectionValidationError, match="test-blocked.yaml: 1 request"):
        validate_collection(tmp_path)


def test_seat_release_waits_for_onboard_departure(tmp_path: Path) -> None:
    # Releasing the full party takes 60 s of driving, but the rider leaves at 100 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 4},
        request_overrides={"party_size": 4, "latest_pickup_time_ms": 75_000},
        onboard_requests=[
            _onboard_request(
                party_size=4,
                earliest_pickup_time_ms=100_000,
                pickup_time_ms=100_000,
                pickup_departure_time_ms=100_000,
            )
        ],
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


@pytest.mark.parametrize("entry", [None, "", 3])
def test_validator_requires_instance_path_strings(tmp_path: Path, entry: object) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    collection["instances"].append(entry)
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match="nonempty path strings"):
        validate_collection(tmp_path)


def test_validator_rejects_parent_directory_segments(tmp_path: Path) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    collection["artifacts"]["test.requests"]["files"][0]["path"] = (
        "tables/sub/../requests.parquet"
    )
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match="escapes collection root"):
        validate_collection(tmp_path)


def test_new_requests_count_elapsed_warm_start_route_time(tmp_path: Path) -> None:
    # The route has run 100 s; the request needs 60 s more against a 120 s limit.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1, "max_route_duration_ms": 120_000},
        request_overrides={"max_ride_time_ms": None},
        onboard_requests=[
            _onboard_request(
                dropoff_node_index=0,
                earliest_pickup_time_ms=-100_000,
                pickup_time_ms=-100_000,
                pickup_departure_time_ms=-100_000,
            )
        ],
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_validator_bounds_all_onboard_dropoffs_per_vehicle(tmp_path: Path) -> None:
    # Each rider alone needs 70 s of a 75 s shift; both together need at least 80 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 2, "shift_end_time_ms": 75_000},
        onboard_requests=[
            _onboard_request(
                onboard_request_index=index,
                onboard_request_id=f"onboard-{index}",
                dropoff_service_time_ms=10_000,
                dropoff_route_position=index + 1,
            )
            for index in range(2)
        ],
    )
    with pytest.raises(CollectionValidationError, match="cannot drop off all onboard riders"):
        validate_collection(tmp_path)


def test_loaded_vehicle_waits_for_onboard_departure_before_leaving(tmp_path: Path) -> None:
    # A spare seat is available, but the vehicle is loading a rider until 100 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1},
        request_overrides={
            "pickup_node_index": 1,
            "dropoff_node_index": 0,
            "latest_pickup_time_ms": 50_000,
        },
        onboard_requests=[
            _onboard_request(
                dropoff_node_index=0,
                earliest_pickup_time_ms=100_000,
                pickup_time_ms=100_000,
                pickup_departure_time_ms=100_000,
            )
        ],
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_onboard_route_bound_includes_travel_between_dropoffs(tmp_path: Path) -> None:
    # Drop-offs at nodes 1 and 2 each fit alone (60 s), but visiting both takes 90 s.
    _write_collection(
        tmp_path,
        node_count=3,
        vehicle_overrides={"initial_load": 2, "shift_end_time_ms": 80_000},
        onboard_requests=[
            _onboard_request(
                onboard_request_index=index,
                onboard_request_id=f"onboard-{index}",
                dropoff_node_index=index + 1,
                dropoff_route_position=index + 1,
            )
            for index in range(2)
        ],
    )
    with pytest.raises(CollectionValidationError, match="cannot drop off all onboard riders"):
        validate_collection(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("path", 3, "one nonempty path or uri"),
        ("sha256", "XYZ", "64 lowercase hex"),
        ("byte_size", "12", "byte_size must be a nonnegative integer"),
        ("row_count", -1, "row_count must be a nonnegative integer"),
    ],
)
def test_validator_type_checks_file_records(
    tmp_path: Path, field: str, value: object, expected_error: str
) -> None:
    _write_collection(tmp_path)
    collection = yaml.safe_load((tmp_path / "collection.yaml").read_text())
    collection["artifacts"]["test.requests"]["files"][0][field] = value
    dump_yaml(tmp_path / "collection.yaml", collection)
    with pytest.raises(CollectionValidationError, match=expected_error):
        validate_collection(tmp_path)


def test_request_serviceability_includes_onboard_dropoffs(tmp_path: Path) -> None:
    # The request and the onboard drop-off each take 60 s alone; together at least 90 s.
    _write_collection(
        tmp_path,
        node_count=3,
        vehicle_overrides={"initial_load": 1, "shift_end_time_ms": 80_000},
        onboard_requests=[_onboard_request(dropoff_node_index=2)],
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_onboard_riders_wait_for_the_latest_departure(tmp_path: Path) -> None:
    # The rider bound for node 1 cannot leave until the other rider departs at 100 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 2, "shift_end_time_ms": 120_000},
        onboard_requests=[
            _onboard_request(onboard_request_index=0, onboard_request_id="onboard-0"),
            _onboard_request(
                onboard_request_index=1,
                onboard_request_id="onboard-1",
                dropoff_node_index=0,
                earliest_pickup_time_ms=100_000,
                pickup_time_ms=100_000,
                pickup_departure_time_ms=100_000,
            ),
        ],
    )
    with pytest.raises(CollectionValidationError, match="cannot be dropped off within"):
        validate_collection(tmp_path)


def test_onboard_ride_deadlines_hold_across_the_shared_route(tmp_path: Path) -> None:
    # Each 50 s ride limit fits a direct 30 s trip, but the second drop-off is 60 s away.
    _write_collection(
        tmp_path,
        node_count=3,
        vehicle_overrides={"initial_load": 2},
        onboard_requests=[
            _onboard_request(
                onboard_request_index=index,
                onboard_request_id=f"onboard-{index}",
                dropoff_node_index=index + 1,
                max_ride_time_ms=50_000,
            )
            for index in range(2)
        ],
    )
    with pytest.raises(CollectionValidationError, match="in any drop-off order"):
        validate_collection(tmp_path)


def test_start_node_pickup_still_waits_for_onboard_departure(tmp_path: Path) -> None:
    # The pickup at the start node can happen at 0 s, but the vehicle leaves at 100 s.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 1},
        request_overrides={"latest_pickup_time_ms": 0, "latest_dropoff_time_ms": 50_000},
        onboard_requests=[
            _onboard_request(
                dropoff_node_index=0,
                earliest_pickup_time_ms=100_000,
                pickup_time_ms=100_000,
                pickup_departure_time_ms=100_000,
            )
        ],
    )
    with pytest.raises(CollectionValidationError, match="within its shift and limits"):
        validate_collection(tmp_path)


def test_colocated_onboard_riders_arrive_together(tmp_path: Path) -> None:
    # Both riders reach node 1 at 30 s, within their 40 s limits, despite 30 s services.
    _write_collection(
        tmp_path,
        vehicle_overrides={"initial_load": 2},
        onboard_requests=[
            _onboard_request(
                onboard_request_index=index,
                onboard_request_id=f"onboard-{index}",
                dropoff_service_time_ms=30_000,
                max_ride_time_ms=40_000,
            )
            for index in range(2)
        ],
    )
    assert validate_collection(tmp_path)["valid"] is True
