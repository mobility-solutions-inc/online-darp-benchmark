import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml

from online_darp_benchmark.convert_ontra_manhattan import (
    HISTORICAL_FLEET_FILENAME,
    POINT_POOL_FILENAME,
    REQUESTS_FILENAME,
    convert,
)
from online_darp_benchmark.parquet_collection import validate_collection


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _source_fixture(root: Path) -> None:
    requests = [
        {
            "request_id": "request-1",
            "passenger_count": 1,
            "origin": {"lat": 40_700_000, "lon": -74_000_000},
            "destination": {"lat": 40_710_000, "lon": -73_990_000},
            "pickup_lb": 1_737_550_800,
            "request_time": 1_737_550_800,
            "pickup_zone_id": 10,
        },
        {
            "request_id": "request-2",
            "passenger_count": 2,
            "origin": {"lat": 40_720_000, "lon": -73_980_000},
            "destination": {"lat": 40_700_000, "lon": -74_000_000},
            "pickup_lb": 1_737_550_860,
            "request_time": 1_737_550_860,
            "pickup_zone_id": 20,
        },
    ]
    vehicles = [
        {
            "vehicle_workflow_id": "vehicle-1",
            "start_time": 1_737_550_800,
            "capacity": 5,
            "location": {"lat": 40_730_000, "lon": -73_970_000},
            "route": {"shift_end_time": 1_737_554_400},
        }
    ]
    pool = {
        "points": [
            {"lat": 40_700_000, "lon": -74_000_000, "zone_id": 10, "pool_index": 0},
            {"lat": 40_705_000, "lon": -73_995_000, "zone_id": 10, "pool_index": 1},
            {"lat": 40_710_000, "lon": -73_990_000, "zone_id": 30, "pool_index": 0},
            {"lat": 40_720_000, "lon": -73_980_000, "zone_id": 20, "pool_index": 0},
            {"lat": 40_730_000, "lon": -73_970_000, "zone_id": 40, "pool_index": 0},
        ]
    }
    _write_json(root / REQUESTS_FILENAME, requests)
    _write_json(root / HISTORICAL_FLEET_FILENAME, vehicles)
    _write_json(root / POINT_POOL_FILENAME, pool)


def test_convert_ontra_manhattan_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "collection"
    source.mkdir()
    _source_fixture(source)

    summary = convert(
        source,
        output,
        "test-version",
        enforce_pins=False,
        balanced_fleet_sizes=(4,),
        matrix_shard_origins=2,
    )

    assert summary == {
        "collection_id": "ontra-manhattan-tlc-2025-01-22-v1",
        "requests": 2,
        "nodes": 5,
        "travel_matrix_rows": 25,
        "fleet_deployments": 2,
        "instances": 2,
        "artifacts": 6,
    }
    assert validate_collection(output)["valid"] is True

    collection = yaml.safe_load((output / "collection.yaml").read_text())
    assert collection["scope"]["official_fleet_deployments"] == 1
    assert collection["scope"]["supplemental_fleet_deployments"] == 1
    assert collection["transformations"][0]["code_version"] == "test-version"

    nodes = pq.read_table(
        output / "tables/networks/pool25-haversine/nodes.parquet"
    ).to_pydict()
    assert "tlc-zone-010-pool-01" in nodes["node_id"]

    matrix_files = collection["artifacts"][
        "ontra-manhattan-tlc-2025-01-22-v1.pool25-haversine.nodes.travel-times"
    ]["files"]
    assert [file["row_count"] for file in matrix_files] == [10, 10, 5]


def test_converter_rejects_nonpositive_matrix_shard_size(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_fixture(source)

    with pytest.raises(ValueError, match="at least one"):
        convert(
            source,
            tmp_path / "collection",
            "test-version",
            enforce_pins=False,
            balanced_fleet_sizes=(4,),
            matrix_shard_origins=0,
        )
