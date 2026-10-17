from pathlib import Path

import pytest

from online_darp_benchmark.convert_eccel import (
    EXPECTED_INSTANCE_STEMS,
    FAMILIES,
    _source_pair_root,
    convert,
)


def _source_fixture(root: Path, omit: str | None = None, extra: str | None = None) -> None:
    for source_family in FAMILIES:
        family_root = _source_pair_root(root, source_family)
        stems = set(EXPECTED_INSTANCE_STEMS[source_family]) - {omit}
        if extra and source_family == "cordeau_laporte_2003":
            stems.add(extra)
        for kind in ("json_static_instances", "json_dynamic_instances"):
            (family_root / kind).mkdir(parents=True)
            for stem in stems:
                (family_root / kind / f"{stem}.json").write_text("{}", encoding="utf-8")


@pytest.mark.parametrize(
    ("omit", "extra", "message"),
    [("b8-96", None, "missing b8-96"), (None, "pr21", "unexpected pr21")],
)
def test_converter_requires_exact_source_instance_set(
    tmp_path: Path, omit: str | None, extra: str | None, message: str
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "collection"
    _source_fixture(source, omit=omit, extra=extra)

    with pytest.raises(ValueError, match=message):
        convert(source, output, "test-version")
    assert not output.exists()


def test_converter_rejects_source_contents_that_differ_from_pin(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "collection"
    _source_fixture(source)

    with pytest.raises(ValueError, match="do not match the pinned"):
        convert(source, output, "test-version")
    assert not output.exists()


def test_converter_requires_source_license(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "collection"
    _source_fixture(source)

    with pytest.raises(FileNotFoundError, match="license is required"):
        convert(source, output, "test-version", enforce_pins=False)
    assert not output.exists()
