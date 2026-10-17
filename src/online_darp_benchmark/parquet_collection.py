"""Reference Parquet writer and validator for RFC-0001 collections."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import sys
import tempfile
import unicodedata
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml
from jsonschema import Draft7Validator


FORMAT_VERSION = "1.0.0-draft.1"
SCHEMA_VERSION = "1.0.0-draft.1"

# GeoParquet 1.1 requires `crs` to be PROJJSON. Generated with
# pyproj.CRS("OGC:CRS84").to_json_dict() (pyproj 3.8.0, PROJ 9.8.1).
OGC_CRS84_PROJJSON: dict[str, Any] = {
    "$schema": "https://proj.org/schemas/v0.7/projjson.schema.json",
    "type": "GeographicCRS",
    "name": "WGS 84 (CRS84)",
    "datum_ensemble": {
        "name": "World Geodetic System 1984 ensemble",
        "members": [
            {
                "name": "World Geodetic System 1984 (Transit)",
                "id": {
                    "authority": "EPSG",
                    "code": 1166
                }
            },
            {
                "name": "World Geodetic System 1984 (G730)",
                "id": {
                    "authority": "EPSG",
                    "code": 1152
                }
            },
            {
                "name": "World Geodetic System 1984 (G873)",
                "id": {
                    "authority": "EPSG",
                    "code": 1153
                }
            },
            {
                "name": "World Geodetic System 1984 (G1150)",
                "id": {
                    "authority": "EPSG",
                    "code": 1154
                }
            },
            {
                "name": "World Geodetic System 1984 (G1674)",
                "id": {
                    "authority": "EPSG",
                    "code": 1155
                }
            },
            {
                "name": "World Geodetic System 1984 (G1762)",
                "id": {
                    "authority": "EPSG",
                    "code": 1156
                }
            },
            {
                "name": "World Geodetic System 1984 (G2139)",
                "id": {
                    "authority": "EPSG",
                    "code": 1309
                }
            },
            {
                "name": "World Geodetic System 1984 (G2296)",
                "id": {
                    "authority": "EPSG",
                    "code": 1383
                }
            }
        ],
        "ellipsoid": {
            "name": "WGS 84",
            "semi_major_axis": 6378137,
            "inverse_flattening": 298.257223563
        },
        "accuracy": "2.0",
        "id": {
            "authority": "EPSG",
            "code": 6326
        }
    },
    "coordinate_system": {
        "subtype": "ellipsoidal",
        "axis": [
            {
                "name": "Geodetic longitude",
                "abbreviation": "Lon",
                "direction": "east",
                "unit": "degree"
            },
            {
                "name": "Geodetic latitude",
                "abbreviation": "Lat",
                "direction": "north",
                "unit": "degree"
            }
        ]
    },
    "scope": "Not known.",
    "area": "World.",
    "bbox": {
        "south_latitude": -90,
        "west_longitude": -180,
        "north_latitude": 90,
        "east_longitude": 180
    },
    "id": {
        "authority": "OGC",
        "code": "CRS84"
    }
}
ROW_GROUP_SIZE = 1_048_576

REQUESTS_SCHEMA = pa.schema(
    [
        pa.field("request_index", pa.int32(), nullable=False),
        pa.field("request_id", pa.string(), nullable=False),
        pa.field("source_request_id", pa.string(), nullable=True),
        pa.field("party_size", pa.int32(), nullable=False),
        pa.field("pickup_node_index", pa.int32(), nullable=False),
        pa.field("dropoff_node_index", pa.int32(), nullable=False),
        pa.field("earliest_pickup_time_ms", pa.int64(), nullable=False),
        pa.field("latest_pickup_time_ms", pa.int64(), nullable=True),
        pa.field("earliest_dropoff_time_ms", pa.int64(), nullable=True),
        pa.field("latest_dropoff_time_ms", pa.int64(), nullable=True),
        pa.field("max_ride_time_ms", pa.int64(), nullable=True),
        pa.field("pickup_service_time_ms", pa.int64(), nullable=False),
        pa.field("dropoff_service_time_ms", pa.int64(), nullable=False),
    ]
)

REVEAL_TIMES_SCHEMA = pa.schema(
    [
        pa.field("request_index", pa.int32(), nullable=False),
        pa.field("base_reveal_time_ms", pa.int64(), nullable=False),
    ]
)

VEHICLES_SCHEMA = pa.schema(
    [
        pa.field("vehicle_index", pa.int32(), nullable=False),
        pa.field("vehicle_id", pa.string(), nullable=False),
        pa.field("source_vehicle_id", pa.string(), nullable=True),
        pa.field("start_node_index", pa.int32(), nullable=False),
        pa.field("end_node_index", pa.int32(), nullable=True),
        pa.field("shift_start_time_ms", pa.int64(), nullable=False),
        pa.field("shift_end_time_ms", pa.int64(), nullable=False),
        pa.field("max_route_duration_ms", pa.int64(), nullable=True),
        pa.field("seat_capacity", pa.int32(), nullable=False),
        pa.field("initial_load", pa.int32(), nullable=False),
    ]
)

ONBOARD_REQUESTS_SCHEMA = pa.schema(
    [
        pa.field("onboard_request_index", pa.int32(), nullable=False),
        pa.field("onboard_request_id", pa.string(), nullable=False),
        pa.field("source_request_id", pa.string(), nullable=True),
        pa.field("party_size", pa.int32(), nullable=False),
        pa.field("pickup_node_index", pa.int32(), nullable=False),
        pa.field("dropoff_node_index", pa.int32(), nullable=False),
        pa.field("earliest_pickup_time_ms", pa.int64(), nullable=False),
        pa.field("pickup_time_ms", pa.int64(), nullable=False),
        pa.field("pickup_departure_time_ms", pa.int64(), nullable=False),
        pa.field("assigned_vehicle_index", pa.int32(), nullable=False),
        pa.field("dropoff_route_position", pa.int32(), nullable=False),
        pa.field("max_ride_time_ms", pa.int64(), nullable=True),
        pa.field("dropoff_service_time_ms", pa.int64(), nullable=False),
    ]
)

NODE_CORE_FIELDS = [
    pa.field("node_index", pa.int32(), nullable=False),
    pa.field("node_id", pa.string(), nullable=False),
    pa.field("source_node_id", pa.string(), nullable=True),
    pa.field("relocation_allowed", pa.bool_(), nullable=False),
]
NODES_MATRIX_SCHEMA = pa.schema(NODE_CORE_FIELDS)
NODES_CARTESIAN_SCHEMA = pa.schema(
    NODE_CORE_FIELDS
    + [
        pa.field("x", pa.float64(), nullable=False),
        pa.field("y", pa.float64(), nullable=False),
    ]
)
NODES_GEOGRAPHIC_SCHEMA = pa.schema(
    NODE_CORE_FIELDS + [pa.field("geometry", pa.binary(), nullable=False)]
)

TRAVEL_TIMES_SCHEMA = pa.schema(
    [
        pa.field("from_node_index", pa.int32(), nullable=False),
        pa.field("to_node_index", pa.int32(), nullable=False),
        pa.field("travel_time_ms", pa.int64(), nullable=False),
        pa.field("distance_mm", pa.int64(), nullable=True),
    ]
)

SCHEMAS = {
    "requests": REQUESTS_SCHEMA,
    "reveal_times": REVEAL_TIMES_SCHEMA,
    "vehicles": VEHICLES_SCHEMA,
    "onboard_requests": ONBOARD_REQUESTS_SCHEMA,
    "nodes_matrix": NODES_MATRIX_SCHEMA,
    "nodes_cartesian": NODES_CARTESIAN_SCHEMA,
    "nodes_geographic": NODES_GEOGRAPHIC_SCHEMA,
    "travel_times": TRAVEL_TIMES_SCHEMA,
}

# The only registered relocation-destination policy; it is part of the fingerprint.
RELOCATION_DESTINATIONS = "nodes.relocation_allowed"

REQUIRED_INSTANCE_ROLES = frozenset(
    {"requests", "reveal_times", "vehicles", "nodes", "travel_times"}
)

SORT_KEYS = {
    "requests": ["request_index"],
    "reveal_times": ["request_index"],
    "vehicles": ["vehicle_index"],
    "onboard_requests": ["onboard_request_index"],
    "nodes": ["node_index"],
    "travel_times": ["from_node_index", "to_node_index"],
}


class CollectionValidationError(ValueError):
    """Raised when a normalized collection violates RFC-0001."""

    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__(yaml.safe_dump(report, sort_keys=False, width=float("inf")))
        self.report = report


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _schema_for(schema_name: str, spatial_profile: str | None) -> pa.Schema:
    if schema_name != "nodes":
        return SCHEMAS[schema_name]
    profile = spatial_profile or "matrix_only"
    profile_key = {
        "matrix_only": "matrix",
        "abstract_cartesian": "cartesian",
        "geographic": "geographic",
    }[profile]
    return SCHEMAS[f"nodes_{profile_key}"]


def _file_metadata(
    schema_name: str,
    collection_id: str,
    artifact_id: str,
    spatial_profile: str | None,
    crs: Mapping[str, Any] | None,
) -> dict[bytes, bytes]:
    metadata = {
        b"online_darp.format_version": FORMAT_VERSION.encode(),
        b"online_darp.schema_name": schema_name.encode(),
        b"online_darp.schema_version": SCHEMA_VERSION.encode(),
        b"online_darp.collection_id": collection_id.encode(),
        b"online_darp.artifact_id": artifact_id.encode(),
    }
    if schema_name == "nodes" and spatial_profile == "geographic":
        if not isinstance(crs, Mapping):
            raise TypeError("geographic nodes require a PROJJSON crs object")
        geo = {
            "version": "1.1.0",
            "primary_column": "geometry",
            "columns": {
                "geometry": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                    "crs": crs,
                }
            },
        }
        metadata[b"geo"] = json.dumps(geo, separators=(",", ":")).encode()
    return metadata


def write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Sequence[Any]] | pa.Table,
    *,
    schema_name: str,
    collection_id: str,
    artifact_id: str,
    spatial_profile: str | None = None,
    crs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one deterministic-profile Parquet artifact and return its file record."""

    schema = _schema_for(schema_name, spatial_profile).with_metadata(
        _file_metadata(schema_name, collection_id, artifact_id, spatial_profile, crs)
    )
    if isinstance(rows, pa.Table):
        table = rows.cast(schema.remove_metadata()).replace_schema_metadata(schema.metadata)
    elif isinstance(rows, Mapping):
        table = pa.Table.from_pydict(rows, schema=schema)
    else:
        table = pa.Table.from_pylist(list(rows), schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    pq.write_table(
        table,
        partial,
        version="1.0",
        data_page_version="1.0",
        compression="zstd",
        compression_level=3,
        use_dictionary=True,
        write_statistics=True,
        use_compliant_nested_type=True,
        store_schema=True,
        row_group_size=ROW_GROUP_SIZE,
    )
    partial.replace(path)
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "row_count": table.num_rows,
    }


IMMUTABLE_VERSION_PATTERN = re.compile(
    r"(?:[0-9a-f]{40}|[0-9a-f]{64}|v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)"
)


def require_converter_version(converter_version: str) -> None:
    """Require a full commit hash or a semantic-version release identifier."""

    if not IMMUTABLE_VERSION_PATTERN.fullmatch(converter_version):
        raise ValueError(
            "converter_version must be an immutable commit or release identifier "
            "(a full commit hash or a semantic version)"
        )


def artifact_record(
    *,
    role: str,
    file_record: Mapping[str, Any],
    collection_root: Path,
    source_sha256: str | Sequence[str] | None = None,
    spatial_profile: str | None = None,
) -> dict[str, Any]:
    record = dict(file_record)
    record["path"] = Path(record["path"]).relative_to(collection_root).as_posix()
    artifact = {
        "role": role,
        "schema_name": role,
        "schema_version": SCHEMA_VERSION,
        "sort_keys": SORT_KEYS[role],
        "files": [record],
    }
    if source_sha256 is not None:
        artifact["source_sha256"] = source_sha256
    if spatial_profile is not None:
        artifact["spatial_profile"] = spatial_profile
    return artifact


def dump_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def physical_problem_sha256(
    components: Mapping[str, str],
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    service_horizon_ms: int,
    relocation_allowed: bool,
) -> str:
    physical_roles = ["requests", "vehicles", "nodes", "travel_times"]
    if "onboard_requests" in components:
        physical_roles.append("onboard_requests")
    value = {
        "format_version": FORMAT_VERSION,
        "components": {
            role: [file["sha256"] for file in artifacts[components[role]]["files"]]
            for role in physical_roles
        },
        "service_horizon_ms": service_horizon_ms,
        "relocation": {
            "allowed": relocation_allowed,
            "destinations": RELOCATION_DESTINATIONS,
        },
    }
    return canonical_sha256(value)


def _normal(value: str) -> bool:
    return value == unicodedata.normalize("NFC", value) and bool(value)


def _check_contiguous(values: list[int], label: str, errors: list[str]) -> None:
    if values != list(range(len(values))):
        errors.append(f"{label} must be sorted, contiguous, and zero-based")


def _package_path(root: Path, relative_path: str) -> Path | None:
    """Resolve a manifest path, or return None if it escapes the package root."""

    if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        return None
    path = (root / relative_path).resolve()
    return path if path.is_relative_to(root.resolve()) else None


EXTENSION_COLUMN_PATTERN = re.compile(r"x_[a-z0-9]+(?:_[a-z0-9]+)*__[a-z0-9]+(?:_[a-z0-9]+)*")


def _projjson_validator() -> Draft7Validator:
    """Validator for the vendored PROJJSON v0.7 schema (MIT, PROJ contributors)."""

    schema_path = Path(__file__).with_name("data") / "projjson-0.7.schema.json"
    return Draft7Validator(json.loads(schema_path.read_text(encoding="utf-8")))


_PROJJSON_VALIDATOR = _projjson_validator()


def _extension_errors(
    schema: pa.Schema, core_names: Sequence[str], declared: Any
) -> list[str]:
    """Check extra columns against the artifact's declared extension columns."""

    if not isinstance(declared, list) or not all(
        isinstance(column, Mapping) for column in declared
    ):
        return ["extension_columns must be a list of mappings"]
    declarations = {column.get("name"): column for column in declared}
    errors = []
    for name, column in declarations.items():
        if not isinstance(name, str) or not EXTENSION_COLUMN_PATTERN.fullmatch(name):
            errors.append(f"extension column {name!r} must match x_<organization>__<column>")
            continue
        missing = [
            key
            for key in ("arrow_type", "nullable", "unit", "semantics", "owner")
            if key not in column
        ]
        if missing:
            errors.append(f"extension column {name} missing {', '.join(missing)}")
        if name not in schema.names:
            errors.append(f"declared extension column {name} is absent")
            continue
        field = schema.field(name)
        if str(field.type) != column.get("arrow_type"):
            errors.append(
                f"extension column {name} type {field.type} is not {column.get('arrow_type')}"
            )
        if column.get("nullable") is False and field.nullable:
            errors.append(f"extension column {name} must be non-nullable")
    for name in schema.names:
        if name not in core_names and name not in declarations:
            errors.append(f"undeclared column {name}")
    return errors


def _geo_metadata_errors(metadata: Mapping[bytes, bytes]) -> list[str]:
    try:
        geo = json.loads(metadata[b"geo"])
        column = geo["columns"][geo["primary_column"]]
    except (KeyError, TypeError, json.JSONDecodeError):
        return ["missing or malformed GeoParquet metadata"]
    errors = []
    if geo.get("version") != "1.1.0" or column.get("encoding") != "WKB":
        errors.append("GeoParquet metadata must be version 1.1.0 with WKB encoding")
    if geo.get("primary_column") != "geometry" or column.get("geometry_types") != ["Point"]:
        errors.append("GeoParquet primary column must be a Point `geometry` column")
    crs = column.get("crs")
    if not isinstance(crs, dict) or any(True for _ in _PROJJSON_VALIDATOR.iter_errors(crs)):
        errors.append("GeoParquet crs must be an explicit PROJJSON object")
    return errors


def _is_point_wkb(value: bytes) -> bool:
    """Return whether *value* is a 2D WKB Point with finite coordinates."""

    if len(value) != 21 or value[0] not in (0, 1):
        return False
    order = "<" if value[0] == 1 else ">"
    geometry_type, x, y = struct.unpack(f"{order}Idd", value[1:])
    return geometry_type == 1 and math.isfinite(x) and math.isfinite(y)


def _download_uri(uri: str, directory: Path) -> Path:
    """Download an immutable HTTPS artifact into *directory*."""

    target = directory / hashlib.sha256(uri.encode()).hexdigest()
    request = urllib.request.Request(uri, headers={"User-Agent": "online-darp-benchmark"})
    with urllib.request.urlopen(request) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    return target


def _uri_error(uri: str) -> str | None:
    parts = urlsplit(uri)
    if parts.scheme != "https" or not parts.hostname:
        return "artifact uri must be an absolute https URL"
    segments = parts.path.split("/")
    if "latest" in (segment.lower() for segment in segments):
        return "artifact uri must not be an unversioned latest URL"
    host = (parts.hostname or "").lower()
    ref = None
    if host == "raw.githubusercontent.com" and len(segments) > 3:
        ref = segments[3]
    elif host in {"github.com", "gitlab.com"}:
        for marker in ("raw", "blob"):
            if marker in segments[3:]:
                position = segments.index(marker, 3) + 1
                ref = segments[position] if position < len(segments) else ""
                break
    if ref is not None and not (
        len(ref) in (40, 64) and all(character in "0123456789abcdef" for character in ref)
    ):
        return "artifact uri must pin a full commit hash, not a branch or tag"
    return None


def _instance_errors(instance: Any, collection_id: Any) -> list[str]:
    """Check the instance manifest fields the validator relies on."""

    if not isinstance(instance, Mapping):
        return ["instance manifest must be a mapping"]
    if instance.get("format_version") != FORMAT_VERSION:
        return [f"unsupported format_version: {instance.get('format_version')}"]
    errors = [
        f"missing {key}"
        for key in (
            "instance_id",
            "physical_problem_id",
            "physical_problem_sha256",
            "problem_family",
            "tier",
        )
        if not instance.get(key)
    ]
    if instance.get("collection_id") != collection_id:
        errors.append(f"collection_id must be {collection_id!r}")
    components = instance.get("components")
    if not isinstance(components, Mapping):
        errors.append("components must be a mapping")
    else:
        if missing := sorted(REQUIRED_INSTANCE_ROLES - set(components)):
            errors.append(f"missing components {', '.join(missing)}")
        if unknown := sorted(set(components) - REQUIRED_INSTANCE_ROLES - {"onboard_requests"}):
            errors.append(f"unknown components {', '.join(unknown)}")
    sections = {}
    for key in ("time", "spatial", "relocation"):
        section = instance.get(key)
        if not isinstance(section, Mapping):
            errors.append(f"{key} must be a mapping")
            section = {}
        sections[key] = section
    horizon = sections["time"].get("service_horizon_ms")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 0:
        errors.append("time.service_horizon_ms must be a nonnegative integer")
    if not isinstance(sections["spatial"].get("profile"), str):
        errors.append("spatial.profile must be declared")
    if not isinstance(sections["relocation"].get("allowed"), bool):
        errors.append("relocation.allowed must be a boolean")
    if sections["relocation"].get("destinations") != RELOCATION_DESTINATIONS:
        errors.append(f"relocation.destinations must be {RELOCATION_DESTINATIONS!r}")
    return errors


def _manifest_errors(collection: Any) -> list[str]:
    """Check the collection manifest fields RFC-0001 requires."""

    if not isinstance(collection, Mapping):
        return ["collection.yaml must be a mapping"]
    errors = [
        f"collection.yaml missing {key}"
        for key in ("format_version", "collection_id", "collection_version")
        if not collection.get(key)
    ]
    source = collection.get("source")
    if not isinstance(source, Mapping):
        errors.append("collection.yaml missing source")
    else:
        errors.extend(
            f"collection.yaml missing source.{key}"
            for key in ("source_id", "source_release", "canonical_url", "citations")
            if not source.get(key)
        )
    license_record = collection.get("license")
    if not isinstance(license_record, Mapping) or not license_record.get("spdx_or_name"):
        errors.append("collection.yaml missing license.spdx_or_name")
    elif not isinstance(license_record.get("notice_paths"), list):
        errors.append("collection.yaml license.notice_paths must be a list")
    transformations = collection.get("transformations")
    if not isinstance(transformations, list) or not transformations:
        errors.append("collection.yaml missing transformations")
    else:
        for index, transformation in enumerate(transformations):
            for key in (
                "transformation_id",
                "code_url",
                "code_version",
                "parameters",
                "random_seed",
                "deterministic",
            ):
                if not isinstance(transformation, Mapping) or key not in transformation:
                    errors.append(f"collection.yaml transformations[{index}] missing {key}")
    if not isinstance(collection.get("instances"), list) or not collection["instances"]:
        errors.append("collection.yaml missing instances")
    elif not all(isinstance(entry, str) and entry for entry in collection["instances"]):
        errors.append("collection.yaml instances must be nonempty path strings")
    artifacts = collection.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        errors.append("collection.yaml missing artifacts")
        return errors
    for artifact_id, artifact in artifacts.items():
        if not isinstance(artifact, Mapping):
            errors.append(f"{artifact_id}: artifact must be a mapping")
            continue
        missing = [
            key
            for key in ("role", "schema_name", "schema_version", "sort_keys", "files")
            if key not in artifact
        ]
        if missing:
            errors.append(f"{artifact_id}: missing {', '.join(missing)}")
            continue
        if artifact["schema_name"] not in SORT_KEYS or artifact["role"] != artifact["schema_name"]:
            errors.append(f"{artifact_id}: unknown or mismatched role/schema_name")
            continue
        if artifact["schema_version"] != SCHEMA_VERSION:
            errors.append(f"{artifact_id}: unsupported schema_version {artifact['schema_version']}")
        if artifact["sort_keys"] != SORT_KEYS[artifact["schema_name"]]:
            errors.append(f"{artifact_id}: sort_keys must be {SORT_KEYS[artifact['schema_name']]}")
        if not isinstance(artifact["files"], list) or not artifact["files"]:
            errors.append(f"{artifact_id}: files must be a nonempty list")
            continue
        for file_record in artifact["files"]:
            missing = [
                key
                for key in ("sha256", "byte_size", "row_count")
                if not isinstance(file_record, Mapping) or key not in file_record
            ]
            if missing:
                errors.append(f"{artifact_id}: file record missing {', '.join(missing)}")
                continue
            locators = [file_record.get(key) for key in ("path", "uri") if key in file_record]
            if len(locators) != 1 or not isinstance(locators[0], str) or not locators[0]:
                errors.append(f"{artifact_id}: file locator must be one nonempty path or uri")
            if not (
                isinstance(file_record["sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", file_record["sha256"])
            ):
                errors.append(f"{artifact_id}: file sha256 must be 64 lowercase hex digits")
            for key in ("byte_size", "row_count"):
                value = file_record[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(f"{artifact_id}: file {key} must be a nonnegative integer")
    return errors


def _artifact_table(
    root: Path,
    collection: Mapping[str, Any],
    artifact_id: str,
    errors: list[str],
    fetch_uri: Callable[[str], Path],
) -> pa.Table | None:
    artifact = collection["artifacts"].get(artifact_id)
    if artifact is None:
        errors.append(f"unknown artifact: {artifact_id}")
        return None
    tables: list[pa.Table] = []
    for file_record in artifact["files"]:
        if ("path" in file_record) == ("uri" in file_record):
            errors.append(f"{artifact_id}: file locator must be exactly one of path or uri")
            continue
        locator = file_record.get("path") or file_record["uri"]
        if "path" in file_record:
            path = _package_path(root, file_record["path"])
            if path is None:
                errors.append(f"artifact path escapes collection root: {locator}")
                continue
            if not path.is_file():
                errors.append(f"missing artifact file: {locator}")
                continue
        else:
            if uri_error := _uri_error(locator):
                errors.append(f"{uri_error}: {locator}")
                continue
            try:
                path = fetch_uri(locator)
            except OSError as error:
                errors.append(f"unretrievable artifact uri: {locator}: {error}")
                continue
        if path.stat().st_size != file_record["byte_size"]:
            errors.append(f"byte size mismatch: {locator}")
        if sha256_file(path) != file_record["sha256"]:
            errors.append(f"SHA-256 mismatch: {locator}")
        try:
            parquet_file = pq.ParquetFile(path)
            table = parquet_file.read()
        except (OSError, pa.ArrowException) as error:
            errors.append(f"unreadable Parquet artifact: {locator}: {error}")
            continue
        metadata = parquet_file.schema_arrow.metadata or {}
        required_metadata = {
            b"online_darp.format_version": FORMAT_VERSION.encode(),
            b"online_darp.schema_name": artifact["schema_name"].encode(),
            b"online_darp.schema_version": artifact["schema_version"].encode(),
            b"online_darp.collection_id": collection["collection_id"].encode(),
            b"online_darp.artifact_id": artifact_id.encode(),
        }
        for key, expected in required_metadata.items():
            if metadata.get(key) != expected:
                errors.append(f"metadata mismatch for {key.decode()}: {locator}")
        if artifact.get("spatial_profile") == "geographic":
            errors.extend(
                f"{message}: {locator}" for message in _geo_metadata_errors(metadata)
            )
            if "geometry" in table.column_names and not all(
                isinstance(value, bytes) and _is_point_wkb(value)
                for value in table.column("geometry").to_pylist()
            ):
                errors.append(f"geometry values must be finite 2D WKB Points: {locator}")
        if table.num_rows != file_record["row_count"]:
            errors.append(f"row count mismatch: {locator}")
        expected_schema = _schema_for(
            artifact["schema_name"], artifact.get("spatial_profile")
        ).remove_metadata()
        core_names = expected_schema.names
        if not set(core_names) <= set(table.column_names) or not table.select(
            core_names
        ).schema.remove_metadata().equals(expected_schema, check_metadata=False):
            errors.append(f"schema mismatch: {locator}")
            continue
        if extension_errors := _extension_errors(
            table.schema, core_names, artifact.get("extension_columns", [])
        ):
            errors.extend(f"{message}: {locator}" for message in extension_errors)
            continue
        for name in table.column_names:
            column = table.column(name)
            if (
                pa.types.is_floating(column.type)
                and pc.all(pc.is_finite(column)).as_py() is False
            ):
                errors.append(f"non-finite {name} values: {locator}")
        tables.append(table)
    # Semantic checks run only when every file is present, readable, and
    # schema-valid; the failures above are already reported.
    if not tables or len(tables) != len(artifact["files"]):
        return None
    return pa.concat_tables(tables)


def _artifact_local_errors(
    artifact_id: str, role: str, value: dict[str, list[Any]]
) -> list[str]:
    """Check one table's own keys and semantics, independent of any instance."""

    errors: list[str] = []
    keys = {
        "requests": ("request_index", "request_id"),
        "vehicles": ("vehicle_index", "vehicle_id"),
        "nodes": ("node_index", "node_id"),
        "onboard_requests": ("onboard_request_index", "onboard_request_id"),
        "reveal_times": ("request_index", None),
    }
    if role in keys:
        index_name, id_name = keys[role]
        _check_contiguous(value[index_name], f"{artifact_id}: {index_name}", errors)
        if id_name is not None and (
            len(set(value[id_name])) != len(value[id_name])
            or not all(_normal(item) for item in value[id_name])
        ):
            errors.append(f"{artifact_id}: invalid or duplicate {id_name}")

    if role == "requests":
        requests = value
        if any(item < 1 for item in requests["party_size"]):
            errors.append(f"{artifact_id}: party_size below one")
        if any(item < 0 for item in requests["earliest_pickup_time_ms"]):
            errors.append(f"{artifact_id}: negative earliest pickup time")
        if any(
            item < 0
            for item in requests["pickup_service_time_ms"] + requests["dropoff_service_time_ms"]
        ):
            errors.append(f"{artifact_id}: negative service time")
        if any(item is not None and item < 1 for item in requests["max_ride_time_ms"]):
            errors.append(f"{artifact_id}: nonpositive maximum ride time")
        for row in range(len(requests["request_index"])):
            for lower_name, upper_name in (
                ("earliest_pickup_time_ms", "latest_pickup_time_ms"),
                ("earliest_dropoff_time_ms", "latest_dropoff_time_ms"),
            ):
                lower = requests[lower_name][row]
                upper = requests[upper_name][row]
                if lower is not None and upper is not None and lower > upper:
                    errors.append(f"{artifact_id}: reversed request time window")
    elif role == "vehicles":
        vehicles = value
        if any(item < 1 for item in vehicles["seat_capacity"]):
            errors.append(f"{artifact_id}: vehicle capacity below one")
        if any(item < 0 for item in vehicles["initial_load"]):
            errors.append(f"{artifact_id}: negative initial load")
        if any(
            load > capacity
            for load, capacity in zip(
                vehicles["initial_load"], vehicles["seat_capacity"], strict=True
            )
        ):
            errors.append(f"{artifact_id}: initial load exceeds vehicle capacity")
        if any(
            end < start
            for start, end in zip(
                vehicles["shift_start_time_ms"], vehicles["shift_end_time_ms"], strict=True
            )
        ):
            errors.append(f"{artifact_id}: reversed vehicle shift")
        if any(
            duration is not None and duration < 1
            for duration in vehicles["max_route_duration_ms"]
        ):
            errors.append(f"{artifact_id}: nonpositive maximum route duration")
    elif role == "onboard_requests":
        onboard = value
        if any(item < 1 for item in onboard["party_size"]):
            errors.append(f"{artifact_id}: party_size below one")
        if any(item < 1 for item in onboard["dropoff_route_position"]):
            errors.append(f"{artifact_id}: route position below one")
        if any(item < 0 for item in onboard["dropoff_service_time_ms"]):
            errors.append(f"{artifact_id}: negative service time")
        if any(
            not earliest <= pickup <= departure
            for earliest, pickup, departure in zip(
                onboard["earliest_pickup_time_ms"],
                onboard["pickup_time_ms"],
                onboard["pickup_departure_time_ms"],
                strict=True,
            )
        ):
            errors.append(f"{artifact_id}: impossible onboard pickup chronology")
        if any(item is not None and item < 1 for item in onboard["max_ride_time_ms"]):
            errors.append(f"{artifact_id}: nonpositive maximum ride time")
    elif role == "travel_times":
        keys = list(zip(value["from_node_index"], value["to_node_index"], strict=True))
        if any(previous >= current for previous, current in zip(keys, keys[1:])):
            errors.append(f"{artifact_id}: travel keys must be unique and sorted")
        if any(
            origin == destination and travel != 0
            for (origin, destination), travel in zip(keys, value["travel_time_ms"], strict=True)
        ):
            errors.append(f"{artifact_id}: nonzero travel matrix diagonal")
        if any(item < 0 for item in value["travel_time_ms"]):
            errors.append(f"{artifact_id}: negative travel time")
        if any(item is not None and item < 0 for item in value["distance_mm"]):
            errors.append(f"{artifact_id}: negative travel distance")
    return errors


def _onboard_route_errors(
    onboard: Mapping[str, list[Any]],
    vehicles: Mapping[str, list[Any]],
    travel: Mapping[str, list[Any]],
    node_count: int,
) -> list[str]:
    """Check that each vehicle can finish its onboard riders' drop-offs.

    ``dropoff_route_position`` records the source route, not a required order,
    so every bound holds for any drop-off order. A vehicle leaves its start node
    no earlier than time zero, its shift start, and its latest onboard
    departure; riders dropped at the start node need no departure. Each
    distinct drop-off node is entered once, by at least its cheapest arc from
    the start or another drop-off, so no triangle inequality is assumed.
    """

    times = travel["travel_time_ms"]
    riders_by_vehicle: dict[int, list[int]] = {}
    for row, vehicle in enumerate(onboard["assigned_vehicle_index"]):
        riders_by_vehicle.setdefault(vehicle, []).append(row)
    expired = unreachable = overloaded = late = 0
    for vehicle, rows in riders_by_vehicle.items():
        start_node = vehicles["start_node_index"][vehicle]
        end_node = vehicles["end_node_index"][vehicle]
        shift_start = max(0, vehicles["shift_start_time_ms"][vehicle])
        shift_end = vehicles["shift_end_time_ms"][vehicle]
        max_duration = vehicles["max_route_duration_ms"][vehicle]
        departures = [onboard["pickup_departure_time_ms"][row] for row in rows]
        leave = max(shift_start, max(departures))
        route_start = min(0, min(departures))
        drop_nodes = {onboard["dropoff_node_index"][row] for row in rows}

        def end_leg(node: int) -> int:
            return 0 if end_node is None else times[node * node_count + end_node]

        # Each rider alone: drive straight to the drop-off (and home).
        for row in rows:
            node = onboard["dropoff_node_index"][row]
            departure = (
                max(shift_start, onboard["pickup_departure_time_ms"][row])
                if node == start_node
                else leave
            )
            arrival = departure + times[start_node * node_count + node]
            max_ride = onboard["max_ride_time_ms"][row]
            deadline = onboard["pickup_departure_time_ms"][row] + (max_ride or 0)
            if max_ride is not None and arrival > deadline:
                expired += 1
            finish = arrival + onboard["dropoff_service_time_ms"][row] + end_leg(node)
            if finish > shift_end or (
                max_duration is not None and finish - route_start > max_duration
            ):
                unreachable += 1
        if len(rows) < 2:
            continue

        # All riders together, in any order.
        entry_costs = {
            node: 0
            if node == start_node
            else min(
                times[origin * node_count + node]
                for origin in ({start_node} | drop_nodes) - {node}
            )
            for node in drop_nodes
        }
        services = sorted(onboard["dropoff_service_time_ms"][row] for row in rows)
        work = (
            sum(entry_costs.values())
            + sum(services)
            + (min(end_leg(node) for node in drop_nodes) if end_node is not None else 0)
        )
        # Drop-offs at the start node can be served while waiting to leave.
        at_start = sum(
            onboard["dropoff_service_time_ms"][row]
            for row in rows
            if onboard["dropoff_node_index"][row] == start_node
        )
        finish = (
            max(shift_start + work, leave + work - at_start)
            if drop_nodes - {start_node}
            else shift_start + work
        )
        if finish > shift_end or (
            max_duration is not None and finish - route_start > max_duration
        ):
            overloaded += 1

        # Ride deadlines, per distinct drop-off node (riders there arrive
        # together): in any order, the j-th node is reached no earlier than the
        # j smallest entry costs plus the j - 1 smallest per-node service totals,
        # so the j-th earliest node deadline must be at least that late.
        node_deadlines: dict[int, int] = {}
        node_services: dict[int, int] = {}
        for row in rows:
            node = onboard["dropoff_node_index"][row]
            node_services[node] = (
                node_services.get(node, 0) + onboard["dropoff_service_time_ms"][row]
            )
            if onboard["max_ride_time_ms"][row] is not None:
                deadline = (
                    onboard["pickup_departure_time_ms"][row] + onboard["max_ride_time_ms"][row]
                )
                node_deadlines[node] = min(deadline, node_deadlines.get(node, deadline))
        if node_deadlines:
            costs = sorted(entry_costs.values())
            stop_services = sorted(node_services.values())
            # After leaving, only non-start stops' services remain; at most one
            # earlier stop (the start node) can be served before leaving.
            away_services = sorted(
                service for node, service in node_services.items() if node != start_node
            )
            start_stops = 1 if start_node in node_services else 0
            for index, deadline in enumerate(sorted(node_deadlines.values())):
                travel_so_far = sum(costs[: index + 1])
                earliest = shift_start + travel_so_far + sum(stop_services[:index])
                if travel_so_far:
                    earliest = max(
                        earliest,
                        leave
                        + travel_so_far
                        + sum(away_services[: max(0, index - start_stops)]),
                    )
                if deadline < earliest:
                    late += 1
                    break

    messages = []
    if expired:
        messages.append(
            f"{expired} onboard rider(s) cannot reach drop-off within max_ride_time_ms"
        )
    if unreachable:
        messages.append(
            f"{unreachable} onboard rider(s) cannot be dropped off within the assigned "
            "vehicle's shift and route duration"
        )
    if overloaded:
        messages.append(
            f"{overloaded} vehicle(s) cannot drop off all onboard riders within the shift "
            "and route duration"
        )
    if late:
        messages.append(
            f"{late} vehicle(s) cannot meet every onboard rider's max_ride_time_ms in any "
            "drop-off order"
        )
    return messages


def _shared_route_finish(
    remaining: pa.Table,
    times: pa.ChunkedArray,
    node_count: int,
    start_node: int,
    end_node: int | None,
    drops: Sequence[tuple[int, int, int, int]],
    departure: int,
) -> pa.ChunkedArray:
    """Lower-bound when a route serving each request and all onboard drop-offs ends.

    Every node the route visits is entered once, by at least its cheapest arc
    from a node that may precede it: the start, an onboard drop-off, or (for
    drop-offs and the request drop-off) the request pickup. Services are
    added once each, and the route leaves no earlier than its latest onboard
    departure unless it never leaves the start node.
    """

    pickup, dropoff = remaining["pickup"], remaining["dropoff"]
    drop_nodes = {node for node, *_ in drops}

    def arc(origins: Any, destinations: Any) -> Any:
        return pc.take(times, pc.add(pc.multiply(origins, node_count), destinations))

    def cheapest_from(nodes: set[int], destinations: Any) -> Any:
        best = None
        for node in nodes:
            leg = pc.take(times, pc.add(destinations, node * node_count))
            best = leg if best is None else pc.min_element_wise(best, leg)
        return best

    def zero_where(mask: Any, values: Any) -> Any:
        return pc.if_else(mask, 0, values)

    def at_known_stop(nodes: Any) -> Any:
        mask = pc.equal(nodes, start_node)
        for node in drop_nodes:
            mask = pc.or_(mask, pc.equal(nodes, node))
        return mask

    entry_pickup = zero_where(
        at_known_stop(pickup), cheapest_from({start_node} | drop_nodes, pickup)
    )
    entry_dropoff = zero_where(
        pc.or_(at_known_stop(dropoff), pc.equal(dropoff, pickup)),
        pc.min_element_wise(arc(pickup, dropoff), cheapest_from(drop_nodes, dropoff)),
    )
    total = pc.add(
        pc.add(entry_pickup, entry_dropoff),
        pc.add(remaining["pickup_and_ride"], remaining["dropoff_service"]),
    )
    # pickup_and_ride already counts the direct trip; keep only its service part.
    total = pc.subtract(total, arc(pickup, dropoff))
    for node in drop_nodes - {start_node}:
        static = min(
            times[origin * node_count + node].as_py()
            for origin in ({start_node} | drop_nodes) - {node}
        )
        entry = pc.min_element_wise(
            pc.min_element_wise(
                pc.take(times, pc.add(pc.multiply(pickup, node_count), node)),
                pc.take(times, pc.add(pc.multiply(dropoff, node_count), node)),
            ),
            static,
        )
        total = pc.add(total, entry)
    total = pc.add(total, sum(service for _, service, _, _ in drops))
    if end_node is not None:
        home = pc.take(times, pc.add(pc.multiply(dropoff, node_count), end_node))
        for node in drop_nodes:
            home = pc.min_element_wise(home, times[node * node_count + end_node].as_py())
        total = pc.add(total, home)
    leave = max(departure, max(drop[3] for drop in drops))
    leaves = pc.or_(
        pc.or_(pc.not_equal(pickup, start_node), pc.not_equal(dropoff, start_node)),
        pa.scalar(bool(drop_nodes - {start_node})),
    )
    # Service at the start node can happen while waiting to leave: onboard
    # drop-offs there, the new pickup there, and its drop-off if both are there.
    pickup_at_start = pc.equal(pickup, start_node)
    before_leaving = pc.add(
        pc.if_else(
            pickup_at_start,
            pc.subtract(remaining["pickup_and_ride"], remaining["direct"]),
            0,
        ),
        pc.if_else(
            pc.and_(pickup_at_start, pc.equal(dropoff, start_node)),
            remaining["dropoff_service"],
            0,
        ),
    )
    before_leaving = pc.add(
        before_leaving, sum(service for node, service, *_ in drops if node == start_node)
    )
    return pc.max_element_wise(
        pc.add(departure, total),
        pc.if_else(
            leaves,
            pc.add(leave, pc.subtract(total, before_leaving)),
            pc.add(departure, total),
        ),
    )


def _seat_release_lower_bound(
    remaining: pa.Table,
    to_pickup: pa.ChunkedArray,
    times: pa.ChunkedArray,
    node_count: int,
    start_node: int,
    free_seats: int,
    drops: Sequence[tuple[int, int, int, int]],
    departure: int,
) -> pa.ChunkedArray:
    """Lower-bound the time after *departure* to reach each pickup with enough seats.

    A rider cannot be dropped before their pickup departure. A rider alighting
    at the start node waits only for themself; any detour that leaves the start
    node waits for every onboard rider. *to_pickup* already includes that wait
    for pickups away from the start, so the result is never below it.
    """

    leave_wait = max(0, max(drop[3] for drop in drops) - departure)

    def wait_for(node: int, rider_departure: int) -> int:
        own = max(0, rider_departure - departure)
        return own if node == start_node else max(leave_wait, own)

    first_leg = min(times[start_node * node_count + node].as_py() for node, *_ in drops)
    last_leg = None
    single_detour = None
    for node, service, _, rider_departure in drops:
        from_drop = pc.take(times, pc.add(remaining["pickup"], node * node_count))
        last_leg = from_drop if last_leg is None else pc.min_element_wise(last_leg, from_drop)
        via = pc.add(
            from_drop,
            wait_for(node, rider_departure)
            + times[start_node * node_count + node].as_py()
            + service,
        )
        single_detour = via if single_detour is None else pc.min_element_wise(single_detour, via)
    if all(node != start_node for node, *_ in drops):
        first_leg += leave_wait
    largest_parties = sorted((party for _, _, party, _ in drops), reverse=True)
    smallest_services = sorted(service for _, service, _, _ in drops)
    released = [sum(largest_parties[:count]) for count in range(1, len(drops) + 1)]
    shortage = pc.subtract(remaining["party_size"], free_seats)
    # Requests needing more seats than all onboard parties hold fail on capacity
    # elsewhere; give them the all-parties bound. Walking from the most parties
    # down to one leaves the bound for the fewest parties that free enough seats.
    bound = pc.add(pc.add(last_leg, first_leg), sum(smallest_services))
    for count in range(len(drops), 0, -1):
        stops = (
            single_detour
            if count == 1
            else pc.add(pc.add(last_leg, first_leg), sum(smallest_services[:count]))
        )
        bound = pc.if_else(pc.less_equal(shortage, released[count - 1]), stops, bound)
    # Reaching a pickup away from the start still requires leaving it.
    bound = pc.max_element_wise(bound, to_pickup)
    return pc.if_else(pc.greater(shortage, 0), bound, to_pickup)


def _requests_outside_fleet_shifts(
    requests: pa.Table,
    vehicles: pa.Table,
    travel: pa.Table,
    node_count: int,
    onboard: pa.Table | None = None,
) -> int:
    """Count requests that no vehicle can serve alone within its shift and limits.

    A vehicle qualifies if it can reach the pickup by the latest pickup time,
    then complete pickup service and direct travel by the latest drop-off time,
    and finish drop-off service (after any earliest drop-off wait) and travel to
    its terminal within its shift and maximum route duration. Route duration
    counts the drop-off wait that remains even when departure is delayed as
    late as the pickup window allows. If onboard riders leave too few free
    seats, the vehicle must first drop the fewest parties that free enough
    seats; the pickup is delayed by at least the cheapest first leg to, and
    last leg from, an onboard drop-off plus those parties' smallest service
    times (or the exact shortest detour when one party suffices). Other
    constraints are relaxed, so this never rejects a request that the vehicle
    could serve on its own.
    """

    times = travel["travel_time_ms"]
    pickup = pc.cast(requests["pickup_node_index"], pa.int64())
    dropoff = pc.cast(requests["dropoff_node_index"], pa.int64())
    direct = pc.take(times, pc.add(pc.multiply(pickup, node_count), dropoff))
    remaining = pa.table(
        {
            "pickup": pickup,
            "dropoff": dropoff,
            "direct": direct,
            "max_ride": requests["max_ride_time_ms"],
            "party_size": requests["party_size"],
            "earliest": requests["earliest_pickup_time_ms"],
            "latest": requests["latest_pickup_time_ms"],
            "earliest_dropoff": requests["earliest_dropoff_time_ms"],
            "latest_dropoff": requests["latest_dropoff_time_ms"],
            "pickup_and_ride": pc.add(requests["pickup_service_time_ms"], direct),
            "dropoff_service": requests["dropoff_service_time_ms"],
        }
    )
    onboard_dropoffs: dict[int, list[tuple[int, int, int, int]]] = {}
    if onboard is not None:
        for vehicle, node, service, party, departure in zip(
            onboard["assigned_vehicle_index"].to_pylist(),
            onboard["dropoff_node_index"].to_pylist(),
            onboard["dropoff_service_time_ms"].to_pylist(),
            onboard["party_size"].to_pylist(),
            onboard["pickup_departure_time_ms"].to_pylist(),
            strict=True,
        ):
            onboard_dropoffs.setdefault(vehicle, []).append((node, service, party, departure))
    vehicle_groups = set()
    for vehicle, row in enumerate(
        zip(
            *(
                vehicles[name].to_pylist()
                for name in (
                    "seat_capacity",
                    "initial_load",
                    "start_node_index",
                    "end_node_index",
                    "shift_start_time_ms",
                    "shift_end_time_ms",
                    "max_route_duration_ms",
                )
            ),
            strict=True,
        )
    ):
        vehicle_groups.add((*row, tuple(sorted(onboard_dropoffs.get(vehicle, [])))))

    # Most permissive vehicles first, so later groups only see the few requests left.
    def permissiveness(group: tuple[Any, ...]) -> tuple[Any, ...]:
        capacity, load, _, _, shift_start, shift_end, max_duration, _ = group
        return (shift_start, -shift_end, max_duration is not None, load - capacity)

    for group in sorted(vehicle_groups, key=permissiveness):
        if remaining.num_rows == 0:
            break
        capacity, load, start_node, end_node, shift_start, shift_end, max_duration, drops = group
        # The start node is the vehicle's location at simulation time zero.
        departure = max(shift_start, 0)
        to_pickup = pc.take(times, pc.add(remaining["pickup"], start_node * node_count))
        if drops:
            # A vehicle still loading onboard riders cannot leave its start node
            # before they depart; a pickup at the start node needs no departure.
            leave_wait = max(0, max(drop[3] for drop in drops) - departure)
            if leave_wait:
                to_pickup = pc.if_else(
                    pc.equal(remaining["pickup"], start_node),
                    to_pickup,
                    pc.add(to_pickup, leave_wait),
                )
        if load and drops:
            to_pickup = _seat_release_lower_bound(
                remaining,
                to_pickup,
                times,
                node_count,
                start_node,
                capacity - load,
                drops,
                departure,
            )
        arrival = pc.max_element_wise(pc.add(to_pickup, departure), remaining["earliest"])
        dropoff_arrival = pc.add(arrival, remaining["pickup_and_ride"])
        leave = max([departure] + [drop[3] for drop in drops])
        held_ride = None
        if leave > departure:
            # A pickup at the start node can happen while onboard riders are still
            # departing, but the trip to a drop-off elsewhere waits for them.
            held = pc.and_(
                pc.equal(remaining["pickup"], start_node),
                pc.not_equal(remaining["dropoff"], start_node),
            )
            dropoff_arrival = pc.if_else(
                held,
                pc.max_element_wise(dropoff_arrival, pc.add(remaining["direct"], leave)),
                dropoff_arrival,
            )
            # Delaying the pickup toward the leave time shortens the held wait.
            pickup_service = pc.subtract(remaining["pickup_and_ride"], remaining["direct"])
            held_wait = pc.max_element_wise(
                pc.fill_null(
                    pc.subtract(leave, pc.add(remaining["latest"], pickup_service)), 0
                ),
                0,
            )
            held_ride = pc.if_else(held, pc.add(remaining["direct"], held_wait), 0)
        finish = pc.add(
            pc.max_element_wise(
                dropoff_arrival, pc.fill_null(remaining["earliest_dropoff"], dropoff_arrival)
            ),
            remaining["dropoff_service"],
        )
        # Delaying departure until the latest pickup removes waiting before the
        # pickup, but any earliest drop-off wait beyond that is unavoidable.
        unavoidable_wait = pc.fill_null(
            pc.max_element_wise(
                pc.subtract(
                    remaining["earliest_dropoff"],
                    pc.add(remaining["latest"], remaining["pickup_and_ride"]),
                ),
                0,
            ),
            0,
        )
        driving = pc.add(
            pc.add(pc.add(to_pickup, remaining["pickup_and_ride"]), unavoidable_wait),
            remaining["dropoff_service"],
        )
        if end_node is not None:
            to_end = pc.take(
                times, pc.add(pc.multiply(remaining["dropoff"], node_count), end_node)
            )
            finish = pc.add(finish, to_end)
            driving = pc.add(driving, to_end)
        served = pc.and_(
            pc.and_(
                pc.less_equal(remaining["party_size"], capacity),
                pc.fill_null(pc.less_equal(arrival, remaining["latest"]), True),
            ),
            pc.and_(
                pc.fill_null(pc.less_equal(dropoff_arrival, remaining["latest_dropoff"]), True),
                pc.less_equal(finish, shift_end),
            ),
        )
        # A warm-start route has already run since its earliest onboard departure.
        elapsed_before_start = max(0, -min((drop[3] for drop in drops), default=0))
        if max_duration is not None:
            served = pc.and_(
                served, pc.less_equal(pc.add(driving, elapsed_before_start), max_duration)
            )
        if held_ride is not None:
            served = pc.and_(
                served, pc.fill_null(pc.less_equal(held_ride, remaining["max_ride"]), True)
            )
        if drops:
            # The same route must also finish every onboard drop-off.
            shared_finish = _shared_route_finish(
                remaining, times, node_count, start_node, end_node, drops, departure
            )
            served = pc.and_(served, pc.less_equal(shared_finish, shift_end))
            if max_duration is not None:
                served = pc.and_(
                    served,
                    pc.less_equal(
                        pc.add(pc.subtract(shared_finish, departure), elapsed_before_start),
                        max_duration,
                    ),
                )
        remaining = remaining.filter(pc.invert(served))
    return remaining.num_rows


def validate_collection(
    root: Path, *, fetch_uri: Callable[[str], Path] | None = None
) -> dict[str, Any]:
    """Validate package integrity, tables, joins, and core DARP semantics.

    External ``uri`` artifacts are downloaded over HTTPS by default; *fetch_uri*
    may supply another retriever that returns a local file for a URI.
    """

    with tempfile.TemporaryDirectory(prefix="odb-validate-") as download_directory:
        return _validate_collection(
            root,
            fetch_uri or (lambda uri: _download_uri(uri, Path(download_directory))),
        )


def _validate_collection(root: Path, fetch_uri: Callable[[str], Path]) -> dict[str, Any]:
    collection_path = root / "collection.yaml"
    collection = yaml.safe_load(collection_path.read_text(encoding="utf-8"))
    errors: list[str] = _manifest_errors(collection)
    warnings: list[str] = []
    if errors:
        raise CollectionValidationError(
            {
                "collection_id": collection.get("collection_id")
                if isinstance(collection, Mapping)
                else None,
                "valid": False,
                "artifact_count": 0,
                "instance_count": 0,
                "errors": errors,
                "warnings": warnings,
            }
        )
    if collection.get("format_version") != FORMAT_VERSION:
        errors.append(f"unsupported format_version: {collection.get('format_version')}")
    for notice_path in collection.get("license", {}).get("notice_paths", []):
        resolved = _package_path(root, notice_path)
        if resolved is None:
            errors.append(f"license notice path escapes collection root: {notice_path}")
        elif not resolved.is_file():
            errors.append(f"missing license notice: {notice_path}")

    cache: dict[str, pa.Table | None] = {}
    for artifact_id in collection.get("artifacts", {}):
        cache[artifact_id] = _artifact_table(
            root, collection, artifact_id, errors, fetch_uri
        )

    dictionaries = {
        artifact_id: table.to_pydict() if table is not None else None
        for artifact_id, table in cache.items()
    }
    for artifact_id, value in dictionaries.items():
        if value is not None:
            role = collection["artifacts"][artifact_id]["role"]
            errors.extend(_artifact_local_errors(artifact_id, role, value))

    checked_relationships: set[tuple[str, ...]] = set()
    physical_fingerprints: dict[Any, str] = {}
    instance_ids: set[Any] = set()

    for relative_manifest in collection.get("instances", []):
        manifest_path = _package_path(root, relative_manifest)
        if manifest_path is None:
            errors.append(f"instance manifest escapes collection root: {relative_manifest}")
            continue
        if not manifest_path.is_file():
            errors.append(f"missing instance manifest: {relative_manifest}")
            continue
        instance = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if instance_errors := _instance_errors(instance, collection["collection_id"]):
            errors.extend(f"{relative_manifest}: {message}" for message in instance_errors)
            continue
        if instance["instance_id"] in instance_ids:
            errors.append(f"{relative_manifest}: duplicate instance_id {instance['instance_id']!r}")
            continue
        instance_ids.add(instance["instance_id"])
        components = instance["components"]
        mismatched_roles = [
            role
            for role, artifact_id in components.items()
            if collection["artifacts"].get(artifact_id, {}).get("role") != role
        ]
        if mismatched_roles:
            errors.append(
                f"{relative_manifest}: components reference missing or wrong-role "
                f"artifacts: {', '.join(sorted(mismatched_roles))}"
            )
            continue
        values = {role: dictionaries.get(artifact_id) for role, artifact_id in components.items()}
        if any(value is None for value in values.values()):
            errors.append(f"{relative_manifest}: unresolved component")
            continue

        requests = values["requests"]
        reveals = values["reveal_times"]
        vehicles = values["vehicles"]
        nodes = values["nodes"]
        travel = values["travel_times"]
        node_count = len(nodes["node_index"])

        declared_profile = (instance.get("spatial") or {}).get("profile")
        node_profile = collection["artifacts"][components["nodes"]].get(
            "spatial_profile", "matrix_only"
        )
        if declared_profile != node_profile:
            errors.append(
                f"{relative_manifest}: spatial.profile {declared_profile!r} does not "
                f"match nodes artifact profile {node_profile!r}"
            )
        if requests["request_index"] and not vehicles["vehicle_index"]:
            errors.append(f"{relative_manifest}: requests have no vehicles to serve them")

        request_id = components["requests"]
        reveal_id = components["reveal_times"]
        demand_reveal_key = ("demand-reveal", request_id, reveal_id)
        if demand_reveal_key not in checked_relationships:
            checked_relationships.add(demand_reveal_key)
            if requests["request_index"] != reveals["request_index"]:
                errors.append(f"{relative_manifest}: reveal rows do not match requests")
            else:
                for row, latest in enumerate(requests["latest_pickup_time_ms"]):
                    if latest is not None and reveals["base_reveal_time_ms"][row] > latest:
                        warnings.append(
                            f"{request_id}: request {row} reveals after pickup window"
                        )

        fleet_id = components["vehicles"]

        shift_key = (
            "request-shifts",
            request_id,
            fleet_id,
            components["travel_times"],
            components.get("onboard_requests", ""),
        )
        referenced_nodes = pa.chunked_array(
            [
                *cache[request_id]["pickup_node_index"].chunks,
                *cache[request_id]["dropoff_node_index"].chunks,
                *cache[fleet_id]["start_node_index"].chunks,
                *pc.drop_null(cache[fleet_id]["end_node_index"]).chunks,
                *(
                    cache[components["onboard_requests"]]["dropoff_node_index"].chunks
                    if "onboard_requests" in components
                    and cache.get(components["onboard_requests"]) is not None
                    else []
                ),
            ],
            type=pa.int32(),
        )
        if (
            shift_key not in checked_relationships
            and requests["request_index"]
            and vehicles["vehicle_index"]
            and len(travel["travel_time_ms"]) == node_count * node_count
            and pc.min(referenced_nodes).as_py() >= 0
            and pc.max(referenced_nodes).as_py() < node_count
        ):
            checked_relationships.add(shift_key)
            unserved = _requests_outside_fleet_shifts(
                cache[request_id],
                cache[fleet_id],
                cache[components["travel_times"]],
                node_count,
                cache.get(components["onboard_requests"])
                if "onboard_requests" in components
                else None,
            )
            if unserved:
                errors.append(
                    f"{relative_manifest}: {unserved} request(s) cannot be served by any "
                    "vehicle within its shift and limits"
                )

        capacity_key = ("request-capacity", request_id, fleet_id)
        if capacity_key not in checked_relationships and vehicles["seat_capacity"]:
            checked_relationships.add(capacity_key)
            largest_vehicle = max(vehicles["seat_capacity"])
            if any(value > largest_vehicle for value in requests["party_size"]):
                errors.append(
                    f"{relative_manifest}: request party_size exceeds every vehicle capacity"
                )

        matrix_key = ("matrix", components["nodes"], components["travel_times"])
        if matrix_key not in checked_relationships:
            checked_relationships.add(matrix_key)
            if len(travel["from_node_index"]) != node_count * node_count:
                errors.append(f"{relative_manifest}: travel matrix is not K squared")
            else:
                for offset, (origin, destination) in enumerate(
                    zip(travel["from_node_index"], travel["to_node_index"], strict=True)
                ):
                    if origin != offset // node_count or destination != offset % node_count:
                        errors.append(
                            f"{relative_manifest}: travel matrix keys are incomplete or unsorted"
                        )
                        break
                for index in range(node_count):
                    if travel["travel_time_ms"][index * node_count + index] != 0:
                        errors.append(f"{relative_manifest}: nonzero travel matrix diagonal")
                        break

        feasibility_key = ("request-feasibility", request_id, components["travel_times"])
        if (
            feasibility_key not in checked_relationships
            and len(travel["travel_time_ms"]) == node_count * node_count
        ):
            checked_relationships.add(feasibility_key)
            window_rows: list[int] = []
            ride_rows: list[int] = []
            for row, (pickup, dropoff) in enumerate(
                zip(requests["pickup_node_index"], requests["dropoff_node_index"], strict=True)
            ):
                if not (0 <= pickup < node_count and 0 <= dropoff < node_count):
                    continue
                direct = travel["travel_time_ms"][pickup * node_count + dropoff]
                earliest_arrival = (
                    requests["earliest_pickup_time_ms"][row]
                    + requests["pickup_service_time_ms"][row]
                    + direct
                )
                latest_dropoff = requests["latest_dropoff_time_ms"][row]
                if latest_dropoff is not None and earliest_arrival > latest_dropoff:
                    window_rows.append(row)
                max_ride = requests["max_ride_time_ms"][row]
                # The ride lasts at least the direct trip, and at least until the
                # earliest drop-off when pickup must end by the latest pickup.
                shortest_ride = direct
                latest_pickup = requests["latest_pickup_time_ms"][row]
                earliest_dropoff = requests["earliest_dropoff_time_ms"][row]
                if latest_pickup is not None and earliest_dropoff is not None:
                    shortest_ride = max(
                        direct,
                        earliest_dropoff
                        - latest_pickup
                        - requests["pickup_service_time_ms"][row],
                    )
                if max_ride is not None and shortest_ride > max_ride:
                    ride_rows.append(row)
            if window_rows:
                errors.append(
                    f"{relative_manifest}: {len(window_rows)} request(s) cannot reach "
                    f"drop-off by latest_dropoff_time_ms, first row {window_rows[0]}"
                )
            if ride_rows:
                errors.append(
                    f"{relative_manifest}: {len(ride_rows)} request(s) have a shortest "
                    f"ride longer than max_ride_time_ms, first row {ride_rows[0]}"
                )

        request_nodes_key = ("request-nodes", request_id, components["nodes"])
        if request_nodes_key not in checked_relationships:
            checked_relationships.add(request_nodes_key)
            if any(
                value < 0 or value >= node_count
                for value in requests["pickup_node_index"] + requests["dropoff_node_index"]
            ):
                errors.append(f"{relative_manifest}: request node foreign key out of range")
        fleet_nodes_key = ("fleet-nodes", fleet_id, components["nodes"])
        if fleet_nodes_key not in checked_relationships:
            checked_relationships.add(fleet_nodes_key)
            fleet_nodes = vehicles["start_node_index"] + [
                value for value in vehicles["end_node_index"] if value is not None
            ]
            if any(value < 0 or value >= node_count for value in fleet_nodes):
                errors.append(f"{relative_manifest}: vehicle node foreign key out of range")

        if "onboard_requests" in components:
            onboard_id = components["onboard_requests"]
            onboard = values["onboard_requests"]
            onboard_key = (
                "onboard-state",
                onboard_id,
                fleet_id,
                components["nodes"],
            )
            if onboard_key not in checked_relationships:
                checked_relationships.add(onboard_key)
                if any(
                    value < 0 or value >= node_count
                    for value in onboard["pickup_node_index"] + onboard["dropoff_node_index"]
                ):
                    errors.append(f"{onboard_id}: node foreign key out of range")
                if any(
                    value < 0 or value >= len(vehicles["vehicle_index"])
                    for value in onboard["assigned_vehicle_index"]
                ):
                    errors.append(f"{onboard_id}: vehicle foreign key out of range")
                else:
                    loads = [0] * len(vehicles["vehicle_index"])
                    for vehicle_index, party_size in zip(
                        onboard["assigned_vehicle_index"], onboard["party_size"], strict=True
                    ):
                        loads[vehicle_index] += party_size
                    if loads != vehicles["initial_load"]:
                        errors.append(f"{onboard_id}: onboard loads do not match vehicles")
            onboard_deadline_key = (
                "onboard-deadlines",
                onboard_id,
                fleet_id,
                components["travel_times"],
            )
            onboard_rows = range(len(onboard["onboard_request_index"]))
            if (
                onboard_deadline_key not in checked_relationships
                and len(travel["travel_time_ms"]) == node_count * node_count
                and all(
                    0 <= onboard["assigned_vehicle_index"][row] < len(vehicles["vehicle_index"])
                    and 0 <= onboard["dropoff_node_index"][row] < node_count
                    for row in onboard_rows
                )
                and all(
                    0 <= node < node_count
                    for node in vehicles["start_node_index"]
                    + [node for node in vehicles["end_node_index"] if node is not None]
                )
            ):
                checked_relationships.add(onboard_deadline_key)
                errors.extend(
                    f"{onboard_id}: {message}"
                    for message in _onboard_route_errors(onboard, vehicles, travel, node_count)
                )
        elif any(vehicles["initial_load"]):
            errors.append(f"{relative_manifest}: fleet has load but no onboard_requests component")

        expected_fingerprint = physical_problem_sha256(
            components,
            collection["artifacts"],
            service_horizon_ms=instance["time"]["service_horizon_ms"],
            relocation_allowed=instance["relocation"]["allowed"],
        )
        if instance.get("physical_problem_sha256") != expected_fingerprint:
            errors.append(f"{relative_manifest}: physical problem fingerprint mismatch")
        physical_problem_id = instance.get("physical_problem_id")
        known_fingerprint = physical_fingerprints.setdefault(
            physical_problem_id, expected_fingerprint
        )
        if known_fingerprint != expected_fingerprint:
            errors.append(
                f"{relative_manifest}: physical_problem_id {physical_problem_id!r} "
                "is reused for a different physical problem"
            )

    report = {
        "collection_id": collection.get("collection_id"),
        "valid": not errors,
        "artifact_count": len(collection.get("artifacts", {})),
        "instance_count": len(collection.get("instances", [])),
        "errors": errors,
        "warnings": warnings,
    }
    if errors:
        raise CollectionValidationError(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an RFC-0001 Parquet collection")
    parser.add_argument("collection", type=Path, help="collection root containing collection.yaml")
    parser.add_argument("--report", type=Path, help="write the machine-readable YAML report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_collection(args.collection)
    except CollectionValidationError as error:
        if args.report:
            args.report.write_text(str(error), encoding="utf-8")
        print(error, file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, yaml.YAMLError) as error:
        print(error, file=sys.stderr)
        return 1
    rendered = yaml.safe_dump(report, sort_keys=False)
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
