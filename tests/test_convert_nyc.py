from pathlib import Path

import pytest

from online_darp_benchmark.convert_nyc import convert, verify_source


def test_converter_rejects_source_that_differs_from_pin(tmp_path: Path) -> None:
    source = tmp_path / "NYC_Dataset_2015-2016"
    network = source / "1_Network"
    network.mkdir(parents=True)
    (network / "virtual_stops_latlon.geojson").write_text("{}", encoding="utf-8")
    (network / "edge_time_matrix.txt").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="do not match the pinned archive"):
        verify_source(source)
    with pytest.raises(ValueError, match="do not match the pinned archive"):
        convert(source, tmp_path / "collection", "1.0.0")
    assert not (tmp_path / "collection").exists()
